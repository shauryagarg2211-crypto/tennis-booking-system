from flask import Flask, render_template, request, redirect, url_for, flash, session, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from collections import Counter
from io import StringIO
import csv
import os

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key")
app.permanent_session_lifetime = timedelta(days=7)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///bookings.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


db = SQLAlchemy(app)



# ------------------ MODELS ------------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="player")
    building = db.Column(db.String(10), nullable=True)
    flat_number = db.Column(db.String(20), nullable=True)
    mobile_number = db.Column(db.String(20), nullable=False)

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    date = db.Column(db.String(10), nullable=False)
    start = db.Column(db.String(5), nullable=False)
    end = db.Column(db.String(5), nullable=False)
    court = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(20), default="booked")


# ------------------ HELPERS ------------------

def is_conflict(new_start, new_end, existing_start, existing_end):
    return new_start < existing_end and new_end > existing_start



# ------------------ ROUTES ------------------

@app.route("/")
def landing():
    return render_template("landing_page.html")


@app.route("/home")
def home():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    bookings = Booking.query.order_by(Booking.date, Booking.start).all()

    events = []

    for b in bookings:
        if b.status == "booked":
            color = "#d32f2f"
        elif b.status == "attended":
            color = "#1976d2"
        elif b.status == "no-show":
            color = "#f57c00"
        else:
            color = "#757575"

        events.append({
            "id": b.id,
            "title": f"{b.court} | {b.start}-{b.end} | {b.status}",
            "start": f"{b.date}T{b.start}",
            "end": f"{b.date}T{b.end}",
            "color": color
        })

    user_bookings = Booking.query.filter_by(
        user_id=session["user_id"]
    ).order_by(
        Booking.date,
        Booking.start
    ).all()

    today = datetime.today().date()
    today_string = today.strftime("%Y-%m-%d")

    today_used = Booking.query.filter(
        Booking.user_id == session["user_id"],
        Booking.date == today_string,
        Booking.status != "cancelled"
    ).count()

    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    week_used = Booking.query.filter(
        Booking.user_id == session["user_id"],
        Booking.status != "cancelled",
        Booking.date >= week_start.strftime("%Y-%m-%d"),
        Booking.date <= week_end.strftime("%Y-%m-%d")
    ).count()

    no_shows = Booking.query.filter_by(
        user_id=session["user_id"],
        status="no-show"
    ).count()

    upcoming = []
    history = []

    for booking in user_bookings:
        booking_date = datetime.strptime(booking.date, "%Y-%m-%d").date()

        if booking_date >= today:
            upcoming.append(booking)
        else:
            history.append(booking)

    return render_template(
        "index.html",
        events=events,
        bookings=user_bookings,
        upcoming=upcoming,
        history=history,
        today_used=today_used,
        week_used=week_used,
        no_shows=no_shows
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        
        username = request.form["username"].strip()
        password = request.form["password"]
        role = request.form.get("role", "player")
        building = request.form.get("building", "").strip()
        flat_number = request.form.get("flat_number", "").strip()
        mobile_number = request.form["mobile_number"].strip()
        

        if role not in ["player", "guard", "landlord"]:
            role = "player"

        if User.query.filter_by(username=username).first():
            return render_template("register.html", error="Username already exists")


        user = User(
            username=username,
            password=generate_password_hash(password),
            flat_number=flat_number,
            mobile_number=mobile_number,
            role=role,
            building=building
        )

        db.session.add(user)
        db.session.commit()

        flash("Account created successfully.")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session.clear()
            session["user_id"] = user.id
            session["role"] = user.role

            if request.form.get("remember"):
                session.permanent = True

            if user.role == "guard":
                return redirect(url_for("guard"))
            elif user.role == "landlord":
                return redirect(url_for("admin"))
            else:
                return redirect(url_for("home"))

        return render_template("login.html", error="Invalid username or password")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/book", methods=["POST"])
def book():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    no_shows = Booking.query.filter_by(
        user_id=session["user_id"],
        status="no-show"
    ).count()

    if no_shows >= 3:
        flash("Too many no-shows. Booking blocked.")
        return redirect(url_for("home"))

    date_input = request.form["date"]
    start = request.form["start"]
    end = request.form["end"]
    court = request.form["court"]

    start_time = datetime.strptime(start, "%H:%M")
    end_time = datetime.strptime(end, "%H:%M")

    if start_time >= end_time:
        flash("End time must be after start time.")
        return redirect(url_for("home"))

    booking_date = datetime.strptime(date_input, "%Y-%m-%d").date()

    if booking_date < datetime.today().date():
        flash("You cannot book a date in the past.")
        return redirect(url_for("home"))

    daily_bookings = Booking.query.filter_by(
        user_id=session["user_id"],
        date=date_input
    ).filter(
        Booking.status != "cancelled"
    ).count()

    if daily_bookings >= 2:
        flash("You may only make 2 bookings per day.")
        return redirect(url_for("home"))

    week_start = booking_date - timedelta(days=booking_date.weekday())
    week_end = week_start + timedelta(days=6)

    weekly_bookings = Booking.query.filter(
        Booking.user_id == session["user_id"],
        Booking.status != "cancelled",
        Booking.date >= week_start.strftime("%Y-%m-%d"),
        Booking.date <= week_end.strftime("%Y-%m-%d")
    ).count()

    if weekly_bookings >= 5:
        flash("You may only make 5 bookings per week.")
        return redirect(url_for("home"))

    existing = Booking.query.filter_by(
        date=date_input,
        court=court
    ).all()

    for b in existing:
        if b.status == "cancelled":
            continue

        b_start = datetime.strptime(b.start, "%H:%M")
        b_end = datetime.strptime(b.end, "%H:%M")

        if is_conflict(start_time, end_time, b_start, b_end):
            flash("That court is already booked during that time.")
            return redirect(url_for("home"))

    new_booking = Booking(
        user_id=session["user_id"],
        date=date_input,
        start=start,
        end=end,
        court=court,
        status="booked"
    )

    db.session.add(new_booking)
    db.session.commit()


    flash("Booking created successfully.")
    return redirect(url_for("home"))


@app.route("/availability/<date>")
def availability(date):
    courts = ["Court 1", "Court 2"]

    time_slots = [
        ("04:00", "05:00"),
        ("05:00", "06:00"),
        ("06:00", "07:00"),
        ("07:00", "08:00"),
        ("08:00", "09:00"),
        ("09:00", "10:00"),
        ("10:00", "11:00"),
        ("11:00", "12:00"),
        ("12:00", "13:00"),
        ("13:00", "14:00"),
        ("14:00", "15:00"),
        ("15:00", "16:00"),
        ("16:00", "17:00"),
        ("17:00", "18:00"),
        ("18:00", "19:00"),
        ("19:00", "20:00"),
        ("20:00", "21:00"),
        ("21:00", "22:00")
    ]

    bookings = Booking.query.filter_by(date=date).all()
    available = []

    for court in courts:
        for start, end in time_slots:
            start_time = datetime.strptime(start, "%H:%M")
            end_time = datetime.strptime(end, "%H:%M")

            conflict = False

            for b in bookings:
                if b.court != court or b.status == "cancelled":
                    continue

                b_start = datetime.strptime(b.start, "%H:%M")
                b_end = datetime.strptime(b.end, "%H:%M")

                if is_conflict(start_time, end_time, b_start, b_end):
                    conflict = True
                    break

            available.append({
                "court": court,
                "start": start,
                "end": end,
                "available": not conflict
            })

    return {"slots": available}


@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_booking(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    booking = Booking.query.get_or_404(id)

    if booking.user_id != session["user_id"] and session.get("role") != "landlord":
        return "Unauthorized", 403

    if request.method == "POST":
        date_input = request.form["date"]
        start = request.form["start"]
        end = request.form["end"]
        court = request.form["court"]

        start_time = datetime.strptime(start, "%H:%M")
        end_time = datetime.strptime(end, "%H:%M")

        if start_time >= end_time:
            flash("End time must be after start time.")
            return redirect(url_for("edit_booking", id=id))

        existing = Booking.query.filter_by(date=date_input, court=court).all()

        for b in existing:
            if b.id == booking.id or b.status == "cancelled":
                continue

            b_start = datetime.strptime(b.start, "%H:%M")
            b_end = datetime.strptime(b.end, "%H:%M")

            if is_conflict(start_time, end_time, b_start, b_end):
                flash("Time slot already booked.")
                return redirect(url_for("edit_booking", id=id))

        booking.date = date_input
        booking.start = start
        booking.end = end
        booking.court = court

        db.session.commit()
        flash("Booking updated.")
        return redirect(url_for("home"))

    return render_template("edit.html", booking=booking)


@app.route("/delete/<int:id>")
def delete_booking(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    booking = Booking.query.get_or_404(id)

    if booking.user_id != session["user_id"] and session.get("role") != "landlord":
        return "Unauthorized", 403

    db.session.delete(booking)
    db.session.commit()

    flash("Booking deleted.")
    return redirect(url_for("home"))


@app.route("/cancel/<int:id>")
def cancel_booking(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    booking = Booking.query.get_or_404(id)

    if booking.user_id != session["user_id"] and session.get("role") != "landlord":
        return "Unauthorized", 403

    booking.status = "cancelled"
    db.session.commit()

    flash("Booking cancelled.")
    return redirect(url_for("home"))


@app.route("/guard")
def guard():
    if session.get("role") != "guard":
        return "Unauthorized", 403

    search = request.args.get("search", "").strip()
    court_filter = request.args.get("court", "")
    status_filter = request.args.get("status", "")
    selected_date = request.args.get("date", "")

    if not selected_date:
        selected_date = datetime.today().strftime("%Y-%m-%d")

    query = Booking.query.filter_by(date=selected_date)

    if court_filter:
        query = query.filter(Booking.court == court_filter)

    if status_filter:
        query = query.filter(Booking.status == status_filter)

    bookings = query.order_by(Booking.start, Booking.court).all()

    user_lookup = {
        user.id: {
            "username": user.username,
            "building": user.building,
            "flat": user.flat_number,
            "mobile": user.mobile_number
        }
        for user in User.query.all()
    }

    if search:
        bookings = [
            b for b in bookings
            if search.lower() in user_lookup.get(b.user_id, {}).get("username", "").lower()
        ]

    total = len(bookings)
    attended = sum(1 for b in bookings if b.status == "attended")
    no_show = sum(1 for b in bookings if b.status == "no-show")
    booked = sum(1 for b in bookings if b.status == "booked")

    return render_template(
        "guard.html",
        bookings=bookings,
        user_lookup=user_lookup,
        total=total,
        attended=attended,
        no_show=no_show,
        booked=booked,
        selected_date=selected_date,
        search=search,
        court_filter=court_filter,
        status_filter=status_filter
    )


@app.route("/mark/<int:id>/<status>")
def mark_attendance(id, status):
    if session.get("role") != "guard":
        return "Unauthorized", 403

    if status not in ["attended", "no-show", "booked"]:
        return "Invalid status", 400

    booking = Booking.query.get_or_404(id)
    booking.status = status
    db.session.commit()

    flash("Attendance updated.")
    return redirect(url_for("guard"))


@app.route("/admin")
def admin():
    if session.get("role") != "landlord":
        return "Unauthorized", 403

    users = User.query.all()

    search = request.args.get("search", "").strip()
    court_filter = request.args.get("court", "")
    status_filter = request.args.get("status", "")
    date_filter = request.args.get("date", "")

    query = Booking.query

    if court_filter:
        query = query.filter(Booking.court == court_filter)

    if status_filter:
        query = query.filter(Booking.status == status_filter)

    if date_filter:
        query = query.filter(Booking.date == date_filter)

    bookings = query.order_by(Booking.date, Booking.start).all()

    user_lookup = {
        user.id: {
            "username": user.username,
            "building": user.building,
            "flat": user.flat_number,
            "mobile": user.mobile_number
        }
        for user in User.query.all()
    }

    if search:
        bookings = [
            b for b in bookings
            if search.lower() in user_lookup.get(b.user_id, {}).get("username", "").lower()
        ]

    total_bookings = len(bookings)

    court_counts = Counter([b.court for b in bookings])
    most_used_court = court_counts.most_common(1)[0][0] if court_counts else "None"

    hour_counts = Counter([b.start.split(":")[0] + ":00" for b in bookings])
    peak_hour = hour_counts.most_common(1)[0][0] if hour_counts else "None"

    user_counts = Counter([b.user_id for b in bookings])

    if user_counts:
        top_user_id = user_counts.most_common(1)[0][0]
        top_user = User.query.get(top_user_id)
        frequent_user = top_user.username if top_user else "Unknown"
    else:
        frequent_user = "None"

    status_counts = Counter([b.status for b in bookings])
    date_counts = Counter([b.date for b in bookings])

    return render_template(
        "admin.html",
        users=users,
        bookings=bookings,
        user_lookup=user_lookup,
        total_bookings=total_bookings,
        most_used_court=most_used_court,
        peak_hour=peak_hour,
        frequent_user=frequent_user,
        court_labels=list(court_counts.keys()),
        court_values=list(court_counts.values()),
        hour_labels=list(hour_counts.keys()),
        hour_values=list(hour_counts.values()),
        status_labels=list(status_counts.keys()),
        status_values=list(status_counts.values()),
        date_labels=list(date_counts.keys()),
        date_values=list(date_counts.values()),
        search=search,
        court_filter=court_filter,
        status_filter=status_filter,
        date_filter=date_filter
    )


@app.route("/export-bookings")
def export_bookings():
    if session.get("role") != "landlord":
        return "Unauthorized", 403

    bookings = Booking.query.order_by(Booking.date, Booking.start).all()

    user_lookup = {
        user.id: {
            "username": user.username,
            "building": user.building,
            "flat": user.flat_number,
            "mobile": user.mobile_number
        }
        for user in User.query.all()
    }

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Resident",
        "Building",
        "Flat",
        "Mobile",
        "Date",
        "Start",
        "End",
        "Court",
        "Status"
    ])

    for b in bookings:
        info = user_lookup.get(b.user_id, {})

        writer.writerow([
            info.get("username", "Unknown"),
            info.get("building", "-"),
            info.get("flat", "-"),
            info.get("mobile", "-"),
            b.date,
            b.start,
            b.end,
            b.court,
            b.status
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=bookings_export.csv"
        }
    )

@app.route("/change-role/<int:user_id>", methods=["POST"])
def change_role(user_id):
    if session.get("role") != "landlord":
        return "Unauthorized", 403

    user = User.query.get_or_404(user_id)
    new_role = request.form["role"]

    if new_role not in ["player", "guard", "landlord"]:
        flash("Invalid role.")
        return redirect(url_for("admin"))

    user.role = new_role
    db.session.commit()

    flash("User role updated.")
    return redirect(url_for("admin"))


@app.route("/delete-user/<int:user_id>")
def delete_user(user_id):
    if session.get("role") != "landlord":
        return "Unauthorized", 403

    user = User.query.get_or_404(user_id)

    if user.id == session.get("user_id"):
        flash("You cannot delete your own landlord account.")
        return redirect(url_for("admin"))

    Booking.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()

    flash("User deleted.")
    return redirect(url_for("admin"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user = User.query.get_or_404(session["user_id"])
    return render_template("profile.html", user=user)


@app.route("/reset", methods=["GET", "POST"])
def reset():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()

        if not user:
            return render_template("reset.html", error="User not found")

        user.password = generate_password_hash(password)
        db.session.commit()

        flash("Password reset successfully.")
        return redirect(url_for("login"))

    return render_template("reset.html")


with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)