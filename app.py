from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy
from flask import redirect, url_for

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bookings.db'
db = SQLAlchemy(app)

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10))
    start = db.Column(db.String(5))
    end = db.Column(db.String(5))


@app.route('/')
def home():
    bookings = Booking.query.all()
    return render_template('index.html', bookings=bookings)

@app.route('/book', methods=['POST'])
def book():
    date = request.form['date']
    start = request.form['start']
    end = request.form['end']

    existing = Booking.query.filter_by(date=date).all()

    for b in existing:
        if not (end <= b.start or start >= b.end):
            return "❌ Time slot already booked!"

    new_booking = Booking(date=date, start=start, end=end)
    db.session.add(new_booking)
    db.session.commit()
    
    return redirect(url_for('home'))

@app.route('/delete/<int:id>')
def delete(id):
    booking = Booking.query.get_or_404(id)
    db.session.delete(booking)
    db.session.commit()
    return redirect(url_for('home'))


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)