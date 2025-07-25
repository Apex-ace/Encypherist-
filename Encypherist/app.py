# Import os and the necessary functions from python-dotenv
import os
from dotenv import load_dotenv, find_dotenv

# Explicitly find and load the .env file from the project directory.
# The `override=True` parameter ensures that the variables in your .env file
# take precedence over any conflicting system-wide environment variables.
load_dotenv(find_dotenv(), override=True)


from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf.csrf import CSRFProtect
import qrcode
from io import BytesIO
import base64
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import json
import paypalrestsdk
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Configure app secrets and database URI from the loaded environment variables
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'a-strong-default-secret-key-for-development')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# This print statement helps confirm the correct URL is being used.
print(f"--- INFO: Connecting to database with URI: {app.config['SQLALCHEMY_DATABASE_URI']} ---")


# Initialize extensions
csrf = CSRFProtect(app)
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Database Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    # --- CHANGE: Increased password length to accommodate modern hashes ---
    password = db.Column(db.String(256), nullable=False)
    # --------------------------------------------------------------------
    role = db.Column(db.String(20), nullable=False)
    profile_picture = db.Column(db.String(200))
    messages_sent = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy='dynamic')
    messages_received = db.relationship('Message', foreign_keys='Message.receiver_id', backref='receiver', lazy='dynamic')
    notifications = db.relationship('Notification', backref='user', lazy='dynamic')
    notification_preferences = db.relationship('NotificationPreference', backref='user', uselist=False)
    bookings = db.relationship('Booking', backref='user', lazy='dynamic')
    events = db.relationship('Event', foreign_keys='Event.organizer_id', backref='organizer', lazy='dynamic')

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    organizer_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    payment_qr = db.Column(db.String(500))
    total_tickets = db.Column(db.Integer, nullable=False, default=0)
    remaining_tickets = db.Column(db.Integer, nullable=False, default=0)
    is_group_event = db.Column(db.Boolean, default=False)
    min_group_size = db.Column(db.Integer, default=1)
    max_group_size = db.Column(db.Integer, default=1)
    category = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notifications = db.relationship('Notification', backref='event', lazy='dynamic')
    messages = db.relationship('Message', backref='event', lazy='dynamic')

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))
    booking_date = db.Column(db.DateTime, default=datetime.utcnow)
    payment_status = db.Column(db.String(20), default='pending')
    payment_id = db.Column(db.String(100), unique=True, nullable=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    mobile = db.Column(db.String(20), nullable=False)
    branch = db.Column(db.String(50), nullable=False)
    year = db.Column(db.String(10), nullable=False)
    event = db.relationship('Event', backref='bookings', lazy='joined')

class UserActivity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    activity_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(50))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=True)
    type = db.Column(db.String(50))
    title = db.Column(db.String(200))
    content = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    sent = db.Column(db.Boolean, default=False)
    error = db.Column(db.Text, nullable=True)

class NotificationPreference(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    email_notifications = db.Column(db.Boolean, default=True)
    sms_notifications = db.Column(db.Boolean, default=True)
    event_updates = db.Column(db.Boolean, default=True)
    event_reminders = db.Column(db.Boolean, default=True)
    messages = db.Column(db.Boolean, default=True)
    email = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(20), nullable=True)

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))
    rating = db.Column(db.Integer, nullable=False)
    review_text = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref='reviews')
    event = db.relationship('Event', backref='reviews')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Application Routes ---
@app.route('/')
def landing():
    now = datetime.utcnow()
    try:
        past_events = Event.query.filter(Event.date < now).all()
        for event in past_events:
            Booking.query.filter_by(event_id=event.id).delete()
            db.session.delete(event)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f'Error cleaning up past events: {str(e)}')
    
    featured_events = Event.query.filter(
        Event.date > now
    ).order_by(Event.date).limit(3).all()
    
    return render_template('landing.html', featured_events=featured_events)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')

        if not username or not password or not role:
            flash('Please fill in all fields')
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))

        if len(password) < 6:
            flash('Password must be at least 6 characters long')
            return redirect(url_for('register'))

        if role not in ['student', 'organizer']:
            flash('Invalid role selected')
            return redirect(url_for('register'))

        try:
            hashed_password = generate_password_hash(password)
            user = User(username=username, password=hashed_password, role=role)
            db.session.add(user)
            db.session.commit()
            flash('Registration successful! Please login.')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            # This is the important change to print the specific error
            print(f"--- REGISTRATION ERROR: {e} ---")
            flash('An error occurred during registration. Please try again.')
            return redirect(url_for('register'))

    return render_template('register.html')

@app.route('/register_student', methods=['GET', 'POST'])
def register_student():
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        college_name = request.form.get('college_name')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if not all([full_name, email, college_name, password, confirm_password]):
            flash('Please fill in all fields')
            return redirect(url_for('register_student'))

        if password != confirm_password:
            flash('Passwords do not match')
            return redirect(url_for('register_student'))

        if len(password) < 8:
            flash('Password must be at least 8 characters long')
            return redirect(url_for('register_student'))

        if User.query.filter_by(username=email).first():
            flash('Email already registered')
            return redirect(url_for('register_student'))

        try:
            hashed_password = generate_password_hash(password)
            user = User(username=email, password=hashed_password, role='student')
            db.session.add(user)
            db.session.commit()
            flash('Registration successful! Please login.')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred during registration. Please try again.')
            return redirect(url_for('register_student'))

    return render_template('register_student.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Please provide both username and password', 'error')
            return redirect(url_for('login'))
            
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user, remember=True)
            next_page = request.args.get('next')
            flash('Logged in successfully!', 'success')
            
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            
            return redirect(next_page) if next_page else redirect(url_for('home'))
        
        flash('Invalid username or password', 'error')
        return redirect(url_for('login'))
        
    return render_template('login.html')

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return redirect(url_for('landing'))

@app.route('/home')
@login_required
def home():
    now = datetime.utcnow()
    try:
        past_events = Event.query.filter(Event.date < now).all()
        for event in past_events:
            Booking.query.filter_by(event_id=event.id).delete()
            db.session.delete(event)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f'Error cleaning up past events: {str(e)}')
    
    search_query = request.args.get('search', '').strip()
    category = request.args.get('category', 'all')
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    sort_by = request.args.get('sort', 'date')
    
    query = Event.query.filter(Event.date > now)
    
    if search_query:
        search = f"%{search_query}%"
        query = query.filter(
            db.or_(
                Event.title.ilike(search),
                Event.description.ilike(search),
                Event.location.ilike(search)
            )
        )
    
    if category and category != 'all':
        query = query.filter(Event.category == category)
    
    if min_price is not None:
        query = query.filter(Event.price >= min_price)
    if max_price is not None:
        query = query.filter(Event.price <= max_price)
    
    if start_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            query = query.filter(Event.date >= start)
        except ValueError:
            pass
    
    if end_date:
        try:
            end = datetime.strptime(end_date, '%Y-%m-%d')
            end = end.replace(hour=23, minute=59, second=59)
            query = query.filter(Event.date <= end)
        except ValueError:
            pass
    
    if sort_by == 'price':
        query = query.order_by(Event.price)
    elif sort_by == 'popularity':
        subquery = db.session.query(
            Booking.event_id,
            db.func.count(Booking.id).label('booking_count')
        ).group_by(Booking.event_id).subquery()
        
        query = query.outerjoin(
            subquery, Event.id == subquery.c.event_id
        ).order_by(db.desc(subquery.c.booking_count.nullsfirst()))
    else:
        query = query.order_by(Event.date)
    
    categories = db.session.query(Event.category).distinct().all()
    categories = [cat[0] for cat in categories if cat[0]]
    
    events = query.all()
    
    return render_template(
        'home.html',
        events=events,
        now=now,
        search_query=search_query,
        selected_category=category,
        min_price=min_price,
        max_price=max_price,
        start_date=start_date,
        end_date=end_date,
        sort_by=sort_by,
        categories=categories
    )

@app.route('/create_event', methods=['GET', 'POST'])
@login_required
def create_event():
    if current_user.role != 'organizer':
        flash('Only organizers can create events')
        return redirect(url_for('home'))

    if request.method == 'POST':
        try:
            title = request.form.get('title')
            description = request.form.get('description')
            location = request.form.get('location')
            price = request.form.get('price')
            date_str = request.form.get('date')
            total_tickets = request.form.get('total_tickets')
            category = request.form.get('category')
            is_group_event = 'is_group_event' in request.form

            if not all([title, description, location, price, date_str, total_tickets, category]):
                flash('Please fill in all required fields')
                return redirect(url_for('create_event'))

            try:
                price = float(price)
                total_tickets = int(total_tickets)
                if price < 0 or total_tickets < 1:
                    flash('Price and total tickets must be positive numbers')
                    return redirect(url_for('create_event'))
            except ValueError:
                flash('Invalid price or ticket quantity')
                return redirect(url_for('create_event'))

            try:
                event_date = datetime.strptime(date_str, '%Y-%m-%dT%H:%M')
                if event_date < datetime.now():
                    flash('Event date must be in the future')
                    return redirect(url_for('create_event'))
            except ValueError:
                flash('Invalid date format')
                return redirect(url_for('create_event'))

            min_group_size = 1
            max_group_size = 1
            if is_group_event:
                try:
                    min_group_size = int(request.form.get('min_group_size', 2))
                    max_group_size = int(request.form.get('max_group_size', 10))
                    if min_group_size < 2 or max_group_size < min_group_size:
                        flash('Invalid group size settings')
                        return redirect(url_for('create_event'))
                except ValueError:
                    flash('Invalid group size values')
                    return redirect(url_for('create_event'))

            event = Event(
                title=title,
                description=description,
                location=location,
                price=price,
                date=event_date,
                organizer_id=current_user.id,
                total_tickets=total_tickets,
                remaining_tickets=total_tickets,
                is_group_event=is_group_event,
                min_group_size=min_group_size,
                max_group_size=max_group_size,
                category=category,
                status='pending',
                created_at=datetime.utcnow()
            )
            
            db.session.add(event)
            db.session.commit()
            flash('Event created successfully!')
            return redirect(url_for('home'))

        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred while creating the event: {str(e)}')
            return redirect(url_for('create_event'))

    return render_template('create_event.html')

@app.route('/delete_event/<int:event_id>', methods=['POST'])
@login_required
def delete_event(event_id):
    if current_user.role != 'organizer':
        flash('Unauthorized access')
        return redirect(url_for('home'))
    
    event = Event.query.get_or_404(event_id)
    if event.organizer_id != current_user.id:
        flash('You can only delete your own events')
        return redirect(url_for('home'))
    
    Booking.query.filter_by(event_id=event_id).delete()
    db.session.delete(event)
    db.session.commit()
    
    flash('Event deleted successfully')
    return redirect(url_for('home'))

@app.route('/book_event/<int:event_id>', methods=['GET', 'POST'])
@login_required
def book_event(event_id):
    if current_user.role != 'student':
        flash('Only students can book events')
        return redirect(url_for('home'))
    
    event = Event.query.get_or_404(event_id)
    
    if datetime.utcnow() >= event.date:
        flash('Registration closed: Event has already started')
        return redirect(url_for('home'))
    
    if event.remaining_tickets <= 0:
        flash('Event is sold out!')
        return redirect(url_for('home'))

    existing_booking = Booking.query.filter_by(
        user_id=current_user.id,
        event_id=event.id
    ).first()
    
    if existing_booking:
        flash('You have already booked this event')
        return redirect(url_for('home'))
    
    return render_template('booking_form.html', event=event)

@app.route('/payment/<int:event_id>', methods=['GET', 'POST'])
@login_required
def payment(event_id):
    if current_user.role != 'student':
        flash('Only students can book events')
        return redirect(url_for('home'))
    
    event = Event.query.get_or_404(event_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        mobile = request.form.get('mobile')
        branch = request.form.get('branch')
        year = request.form.get('year')

        if not all([name, email, mobile, branch, year]):
            flash('Please fill in all fields')
            return redirect(url_for('book_event', event_id=event_id))

        try:
            booking = Booking(
                user_id=current_user.id,
                event_id=event.id,
                name=name,
                email=email,
                mobile=mobile,
                branch=branch,
                year=year,
                payment_status='pending',
                payment_id='booking_' + str(datetime.utcnow().timestamp()),
                booking_date=datetime.utcnow()
            )
            
            if event.remaining_tickets <= 0:
                flash('Sorry, this event is now sold out')
                return redirect(url_for('home'))
                
            event.remaining_tickets -= 1
            
            db.session.add(booking)
            db.session.commit()
            
            booking.payment_status = 'succeeded'
            db.session.commit()
            
            flash('Booking successful!')
            return redirect(url_for('ticket', event_id=event_id))
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred during booking. Please try again.')
            return redirect(url_for('book_event', event_id=event_id))
    
    return redirect(url_for('submit_booking', event_id=event_id))

@app.route('/submit_booking/<int:event_id>', methods=['POST'])
@login_required
def submit_booking(event_id):
    if current_user.role != 'student':
        flash('Only students can book events')
        return redirect(url_for('home'))
    
    try:
        event = Event.query.get_or_404(event_id)
        
        if event.remaining_tickets <= 0:
            flash('Event is sold out!')
            return redirect(url_for('home'))
        
        booking = Booking(
            user_id=current_user.id,
            event_id=event.id,
            name=request.form['name'],
            email=request.form['email'],
            mobile=request.form['mobile'],
            branch=request.form['branch'],
            year=request.form['year'],
            payment_status='succeeded',
            payment_id='direct_booking_' + str(datetime.utcnow().timestamp()),
            booking_date=datetime.utcnow()
        )
        
        event.remaining_tickets -= 1
        
        db.session.add(booking)
        db.session.commit()
        
        flash('Booking successful!')
        
        return redirect(url_for('ticket', event_id=event_id))
        
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while processing your booking')
        return redirect(url_for('home'))

@app.route('/process_payment/<int:event_id>')
@login_required
def process_payment(event_id):
    if current_user.role != 'student':
        return redirect(url_for('home'))

    event = Event.query.get_or_404(event_id)
    
    if event.remaining_tickets <= 0:
        flash('Event is sold out!')
        return redirect(url_for('home'))

    payment_id = request.args.get('paymentId')
    payer_id = request.args.get('PayerID')
    
    if not payment_id or not payer_id:
        flash('Payment failed')
        return redirect(url_for('home'))

    try:
        payment = paypalrestsdk.Payment.find(payment_id)
        if payment.execute({"payer_id": payer_id}):
            existing_booking = Booking.query.filter_by(
                user_id=current_user.id,
                event_id=event.id
            ).first()
            
            if existing_booking and existing_booking.payment_status == 'succeeded':
                flash('You have already booked this event')
                return redirect(url_for('home'))
            
            if existing_booking:
                booking = existing_booking
            else:
                booking = Booking(
                    user_id=current_user.id,
                    event_id=event.id,
                    payment_status='pending',
                    payment_id=payment_id,
                    booking_date=datetime.utcnow()
                )
                db.session.add(booking)
            
            booking.payment_status = 'succeeded'
            event.remaining_tickets -= 1
            db.session.commit()
            
            return redirect(url_for('ticket', event_id=event_id))
        else:
            flash('Payment failed')
            return redirect(url_for('home'))

    except Exception as e:
        db.session.rollback()
        flash(f'Payment failed: {str(e)}')
        return redirect(url_for('home'))

@app.route('/ticket/<int:event_id>')
@login_required
def ticket(event_id):
    event = Event.query.get_or_404(event_id)
    booking = Booking.query.filter_by(event_id=event_id, user_id=current_user.id).first_or_404()

    if booking.payment_status != 'succeeded':
        flash('Payment not completed')
        return redirect(url_for('payment', event_id=event_id))

    ticket_data = {
        'booking_id': booking.id,
        'event_title': event.title,
        'event_date': event.date.strftime('%Y-%m-%d %H:%M'),
        'booking_date': booking.booking_date.strftime('%Y-%m-%d %H:%M'),
        'attendee': {
            'name': booking.name,
            'email': booking.email,
            'mobile': booking.mobile,
            'branch': booking.branch,
            'year': booking.year
        },
        'payment_status': booking.payment_status,
        'payment_id': booking.payment_id
    }

    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(json.dumps(ticket_data))
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")

    buffered = BytesIO()
    qr_img.save(buffered, format="PNG")
    qr_code = f"data:image/png;base64,{base64.b64encode(buffered.getvalue()).decode()}"

    pdf_buffer = BytesIO()
    c = canvas.Canvas(pdf_buffer, pagesize=letter)
    c.drawString(100, 750, f"Event: {event.title}")
    c.drawString(100, 730, f"Date: {event.date.strftime('%B %d, %Y')}")
    c.drawString(100, 710, f"Time: {event.date.strftime('%I:%M %p')}")
    c.drawString(100, 690, f"Booking ID: {booking.id}")
    c.drawString(100, 670, f"Booking Date: {booking.booking_date.strftime('%B %d, %Y %I:%M %p')}")
    c.drawString(100, 650, f"Attendee: {booking.name}")
    c.drawString(100, 630, f"Email: {booking.email}")
    c.drawString(100, 610, f"Mobile: {booking.mobile}")
    c.drawString(100, 590, f"Branch: {booking.branch}")
    c.drawString(100, 570, f"Year: {booking.year}")
    c.drawString(100, 550, f"Payment Status: {booking.payment_status}")
    c.drawString(100, 530, f"Payment ID: {booking.payment_id}")
    c.save()

    os.makedirs(os.path.join(app.root_path, 'static'), exist_ok=True)
    pdf_filename = f"ticket_{booking.id}.pdf"
    pdf_path = os.path.join(app.static_folder, pdf_filename)
    with open(pdf_path, 'wb') as f:
        f.write(pdf_buffer.getvalue())

    return render_template('ticket.html',
                          event=event,
                          booking=booking,
                          qr_code=qr_code,
                          ticket_pdf_url=url_for('static', filename=pdf_filename))

@app.route('/clear_database', methods=['POST'])
@login_required
def clear_database():
    if current_user.role != 'admin':
        flash('Unauthorized access')
        return redirect(url_for('home'))
        
    try:
        Booking.query.delete()
        Event.query.delete()
        User.query.filter(User.role != 'admin').delete()
        
        db.session.commit()
        flash('Database cleared successfully!')
    except Exception as e:
        db.session.rollback()
        flash(f'Error clearing database: {str(e)}')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        flash('Unauthorized access')
        return redirect(url_for('home'))
    
    total_users = User.query.count()
    total_events = Event.query.count()
    total_bookings = Booking.query.count()
    pending_events = Event.query.filter_by(status='pending').count()
    
    recent_activities = UserActivity.query.order_by(UserActivity.timestamp.desc()).limit(10).all()
    
    events_by_category = db.session.query(
        Event.category, 
        db.func.count(Event.id)
    ).group_by(Event.category).all()
    
    bookings_by_date = db.session.query(
        db.func.date(Booking.booking_date),
        db.func.count(Booking.id)
    ).group_by(db.func.date(Booking.booking_date)).all()
    
    return render_template(
        'admin/dashboard.html',
        total_users=total_users,
        total_events=total_events,
        total_bookings=total_bookings,
        pending_events=pending_events,
        recent_activities=recent_activities,
        events_by_category=events_by_category,
        bookings_by_date=bookings_by_date
    )

@app.route('/admin/users')
@login_required
def admin_users():
    if current_user.role != 'admin':
        flash('Unauthorized access')
        return redirect(url_for('home'))
    
    users = User.query.all()
    return render_template('admin_users.html', users=users)

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
def admin_delete_user(user_id):
    if current_user.role != 'admin':
        flash('Unauthorized access')
        return redirect(url_for('home'))
    
    if current_user.id == user_id:
        flash('Cannot delete your own admin account')
        return redirect(url_for('admin_users'))
    
    user = User.query.get_or_404(user_id)
    
    Booking.query.filter_by(user_id=user_id).delete()
    Event.query.filter_by(organizer_id=user_id).delete()
    db.session.delete(user)
    db.session.commit()
    
    flash('User deleted successfully')
    return redirect(url_for('admin_users'))

@app.route('/admin/delete_event/<int:event_id>', methods=['POST'])
@login_required
def admin_delete_event(event_id):
    if current_user.role != 'admin':
        flash('Unauthorized access')
        return redirect(url_for('home'))
    
    event = Event.query.get_or_404(event_id)
    
    try:
        Booking.query.filter_by(event_id=event_id).delete()
        db.session.delete(event)
        db.session.commit()
        flash('Event deleted successfully')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting event: {str(e)}')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/events')
@login_required
def admin_events():
    if current_user.role != 'admin':
        flash('Unauthorized access')
        return redirect(url_for('home'))
    
    events = Event.query.order_by(Event.created_at.desc()).all()
    return render_template('admin/events.html', events=events)

@app.route('/admin/approve_event/<int:event_id>', methods=['POST'])
@login_required
def approve_event(event_id):
    if current_user.role != 'admin':
        flash('Unauthorized access')
        return redirect(url_for('home'))
    
    event = Event.query.get_or_404(event_id)
    event.status = 'approved'
    db.session.commit()
    
    log_user_activity(
        current_user.id,
        'approve_event',
        f'Approved event: {event.title}'
    )
    
    flash('Event approved successfully')
    return redirect(url_for('admin_events'))

@app.route('/admin/reject_event/<int:event_id>', methods=['POST'])
@login_required
def reject_event(event_id):
    if current_user.role != 'admin':
        flash('Unauthorized access')
        return redirect(url_for('home'))
    
    event = Event.query.get_or_404(event_id)
    event.status = 'rejected'
    db.session.commit()
    
    log_user_activity(
        current_user.id,
        'reject_event',
        f'Rejected event: {event.title}'
    )
    
    flash('Event rejected successfully')
    return redirect(url_for('admin_events'))

@app.route('/admin/activity_log')
@login_required
def activity_log():
    if current_user.role != 'admin':
        flash('Unauthorized access')
        return redirect(url_for('home'))
    
    page = request.args.get('page', 1, type=int)
    activities = UserActivity.query.order_by(
        UserActivity.timestamp.desc()
    ).paginate(page=page, per_page=20)
    
    return render_template('admin/activity_log.html', activities=activities)

@app.route('/admin/generate_report')
@login_required
def generate_report():
    if current_user.role != 'admin':
        flash('Unauthorized access')
        return redirect(url_for('home'))
    
    report_type = request.args.get('type', 'events')
    
    if report_type == 'events':
        events = Event.query.all()
        output = BytesIO()
        c = canvas.Canvas(output, pagesize=letter)
        
        y = 750
        c.drawString(100, y, "Events Report")
        y -= 20
        
        for event in events:
            c.drawString(100, y, f"Event: {event.title}")
            y -= 15
            c.drawString(120, y, f"Date: {event.date}")
            y -= 15
            c.drawString(120, y, f"Status: {event.status}")
            y -= 15
            c.drawString(120, y, f"Tickets: {event.remaining_tickets}/{event.total_tickets}")
            y -= 20
            
            if y < 50:
                c.showPage()
                y = 750
        
        c.save()
        output.seek(0)
        
        log_user_activity(
            current_user.id,
            'generate_report',
            'Generated events report'
        )
        
        return send_file(
            output,
            mimetype='application/pdf',
            as_attachment=True,
            download_name='events_report.pdf'
        )

def log_user_activity(user_id, activity_type, description, ip_address=None):
    try:
        activity = UserActivity(
            user_id=user_id,
            activity_type=activity_type,
            description=description,
            ip_address=ip_address
        )
        db.session.add(activity)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error logging activity: {str(e)}")

def send_notification(user_id, title, content, notification_type, event_id=None):
    try:
        notification = Notification(
            user_id=user_id,
            event_id=event_id,
            type=notification_type,
            title=title,
            content=content
        )
        db.session.add(notification)
        
        prefs = NotificationPreference.query.filter_by(user_id=user_id).first()
        if not prefs:
            prefs = NotificationPreference(user_id=current_user.id)
            db.session.add(prefs)
        
        if notification_type == 'email' and prefs.email_notifications and prefs.email:
            send_email(prefs.email, title, content)
            notification.sent = True
        
        if notification_type == 'sms' and prefs.sms_notifications and prefs.phone:
            send_sms(prefs.phone, content)
            notification.sent = True
        
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Error sending notification: {str(e)}")
        return False

def send_event_update(event_id, title, content):
    event = Event.query.get(event_id)
    if not event:
        return False
    
    bookings = Booking.query.filter_by(event_id=event_id).all()
    
    for booking in bookings:
        send_notification(booking.user_id, title, content, 'in-app', event_id)
        send_notification(booking.user_id, title, content, 'email', event_id)
        send_notification(booking.user_id, title, content, 'sms', event_id)
    
    return True

def send_event_reminder():
    tomorrow = datetime.utcnow() + timedelta(days=1)
    events = Event.query.filter(
        Event.date > datetime.utcnow(),
        Event.date <= tomorrow
    ).all()
    
    for event in events:
        bookings = Booking.query.filter_by(event_id=event.id).all()
        for booking in bookings:
            title = f"Reminder: {event.title} is tomorrow!"
            content = f"Don't forget! {event.title} is happening tomorrow at {event.date.strftime('%I:%M %p')} at {event.location}."
            send_notification(booking.user_id, title, content, 'email', event.id)
            send_notification(booking.user_id, title, content, 'sms', event.id)

# --- FIX: Helper function to get and categorize conversations ---
def get_conversations_and_users(search_query=None):
    """
    Gets existing conversations and/or searches for users.
    Returns categorized lists of conversations.
    """
    organizer_conversations = {}
    student_conversations = {}
    
    user_pool = []
    
    if search_query:
        # If searching, the pool of users is the search result
        user_pool = User.query.filter(
            User.username.ilike(f'%{search_query}%'),
            User.id != current_user.id
        ).all()
    else:
        # If not searching, the pool is users with existing conversations
        sent_to_ids = db.session.query(Message.receiver_id).filter(Message.sender_id == current_user.id)
        received_from_ids = db.session.query(Message.sender_id).filter(Message.receiver_id == current_user.id)
        user_ids = {r for r, in sent_to_ids}.union({s for s, in received_from_ids})
        if user_ids:
            user_pool = User.query.filter(User.id.in_(user_ids)).all()

    for user in user_pool:
        last_message = Message.query.filter(
            db.or_(
                db.and_(Message.sender_id == current_user.id, Message.receiver_id == user.id),
                db.and_(Message.sender_id == user.id, Message.receiver_id == current_user.id)
            )
        ).order_by(Message.timestamp.desc()).first()

        # If searching and no message history, we still show the user
        if not last_message and search_query:
            # Create a placeholder for display
            last_message = Message(content='Start a new conversation!', timestamp=datetime.min)

        if last_message: # Only add users if there's a conversation or it's a search result
            conv_data = {
                'user': user,
                'last_message': last_message,
                'unread': Message.query.filter_by(
                    sender_id=user.id,
                    receiver_id=current_user.id,
                    read=False
                ).count()
            }
            if user.role == 'organizer':
                organizer_conversations[user.id] = conv_data
            else:
                student_conversations[user.id] = conv_data

    # Sort conversations by last message timestamp
    def sort_key(item):
        return item[1]['last_message'].timestamp

    sorted_organizers = dict(sorted(organizer_conversations.items(), key=sort_key, reverse=True))
    sorted_students = dict(sorted(student_conversations.items(), key=sort_key, reverse=True))
    
    return sorted_organizers, sorted_students

@app.route('/messages')
@login_required
def messages():
    try:
        search_query = request.args.get('search', '').strip()
        organizer_conversations, student_conversations = get_conversations_and_users(search_query)
        
        return render_template('messages.html', 
                               organizer_conversations=organizer_conversations,
                               student_conversations=student_conversations,
                               search_query=search_query) # Pass search query back to template
        
    except Exception as e:
        print(f"--- ERROR in /messages: {e} ---") # For debugging
        flash('An error occurred while loading messages')
        return render_template('messages.html', 
                               organizer_conversations=None,
                               student_conversations=None)

@app.route('/messages/<int:user_id>')
@login_required
def conversation(user_id):
    try:
        search_query = request.args.get('search', '').strip()
        other_user = User.query.get_or_404(user_id)
        
        messages = Message.query.filter(
            db.or_(
                db.and_(Message.sender_id == current_user.id, Message.receiver_id == user_id),
                db.and_(Message.sender_id == user_id, Message.receiver_id == current_user.id)
            )
        ).order_by(Message.timestamp.asc()).all()
        
        Message.query.filter_by(
            sender_id=user_id,
            receiver_id=current_user.id,
            read=False
        ).update({'read': True})
        db.session.commit()
        
        organizer_conversations, student_conversations = get_conversations_and_users(search_query)
        
        return render_template('messages.html', 
                             organizer_conversations=organizer_conversations,
                             student_conversations=student_conversations,
                             messages=messages,
                             other_user=other_user,
                             search_query=search_query) # Pass search query back
        
    except Exception as e:
        print(f"--- ERROR in /messages/<user_id>: {e} ---") # For debugging
        flash('An error occurred while loading the conversation')
        return redirect(url_for('messages'))

@app.route('/send_message/<int:user_id>', methods=['POST'])
@login_required
def send_message(user_id):
    try:
        content = request.form.get('content')
        if not content:
            flash('Message cannot be empty')
            return redirect(url_for('conversation', user_id=user_id))
        
        message = Message(
            sender_id=current_user.id,
            receiver_id=user_id,
            content=content,
            timestamp=datetime.utcnow()
        )
        
        db.session.add(message)
        db.session.commit()
        
        receiver_prefs = NotificationPreference.query.filter_by(user_id=user_id).first()
        if receiver_prefs and receiver_prefs.messages:
            send_notification(
                user_id,
                f"New message from {current_user.username}",
                content[:100] + "..." if len(content) > 100 else content,
                'in-app'
            )
        
        return redirect(url_for('conversation', user_id=user_id))
        
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while sending the message')
        return redirect(url_for('conversation', user_id=user_id))

@app.route('/notifications')
@login_required
def notifications():
    page = request.args.get('page', 1, type=int)
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(
        Notification.timestamp.desc()
    ).paginate(page=page, per_page=20)
    
    return render_template('notifications.html', notifications=notifications)

@app.route('/notification_preferences', methods=['GET', 'POST'])
@login_required
def notification_preferences():
    prefs = NotificationPreference.query.filter_by(user_id=current_user.id).first()
    if not prefs:
        prefs = NotificationPreference(user_id=current_user.id)
        db.session.add(prefs)
        db.session.commit()
    
    if request.method == 'POST':
        prefs.email_notifications = 'email_notifications' in request.form
        prefs.sms_notifications = 'sms_notifications' in request.form
        prefs.event_updates = 'event_updates' in request.form
        prefs.event_reminders = 'event_reminders' in request.form
        prefs.messages = 'messages' in request.form
        prefs.email = request.form.get('email')
        prefs.phone = request.form.get('phone')
        
        db.session.commit()
        flash('Notification preferences updated successfully')
        return redirect(url_for('notification_preferences'))
    
    return render_template('notification_preferences.html', preferences=prefs)

def send_email(to_email, subject, content):
    pass

def send_sms(phone_number, message):
    pass

@app.route('/profile')
@login_required
def profile():
    try:
        now = datetime.utcnow()
        if current_user.role == 'organizer':
            events = Event.query.filter_by(organizer_id=current_user.id)\
                .order_by(Event.date.desc())\
                .all()
            
            return render_template('organizer_profile.html',
                                user=current_user,
                                events=events,
                                now=now)
        else:
            bookings = db.session.query(Booking)\
                .join(Event, Booking.event_id == Event.id)\
                .filter(Booking.user_id == current_user.id)\
                .order_by(Booking.booking_date.desc())\
                .all()
            
            return render_template('student_profile.html',
                                user=current_user,
                                bookings=bookings,
                                now=now)
                                
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while loading your profile. Please try again.')
        return redirect(url_for('home'))

@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        try:
            if 'profile_picture' in request.files:
                file = request.files['profile_picture']
                if file and file.filename:
                    filename = secure_filename(file.filename)
                    filename = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{filename}"
                    
                    uploads_dir = os.path.join(app.root_path, 'static', 'uploads')
                    os.makedirs(uploads_dir, exist_ok=True)
                    
                    file.save(os.path.join(uploads_dir, filename))
                    
                    if current_user.profile_picture:
                        try:
                            old_file = os.path.join(uploads_dir, current_user.profile_picture)
                            if os.path.exists(old_file):
                                os.remove(old_file)
                        except Exception as e:
                            print(f"Error deleting old profile picture: {str(e)}")
                    
                    current_user.profile_picture = filename
            
            db.session.commit()
            flash('Profile updated successfully')
            return redirect(url_for('profile'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating profile: {str(e)}')
            return redirect(url_for('edit_profile'))
    
    return render_template('edit_profile.html', user=current_user)

@app.route('/reset_password', methods=['GET', 'POST'])
@login_required
def reset_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if not current_password or not new_password or not confirm_password:
            flash('Please fill in all fields')
            return redirect(url_for('reset_password'))
        
        if not check_password_hash(current_user.password, current_password):
            flash('Current password is incorrect')
            return redirect(url_for('reset_password'))
        
        if new_password != confirm_password:
            flash('New passwords do not match')
            return redirect(url_for('reset_password'))
        
        if len(new_password) < 6:
            flash('New password must be at least 6 characters long')
            return redirect(url_for('reset_password'))
        
        try:
            current_user.password = generate_password_hash(new_password)
            db.session.commit()
            flash('Password updated successfully')
            return redirect(url_for('profile'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating password: {str(e)}')
            return redirect(url_for('reset_password'))
    
    return render_template('reset_password.html')

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        if not email:
            flash('Please enter your email address')
            return redirect(url_for('forgot_password'))
        
        user = User.query.filter_by(username=email).first()
        if not user:
            flash('No account found with that email address')
            return redirect(url_for('forgot_password'))
        
        reset_token = generate_password_hash(str(datetime.utcnow()))
        user.reset_token = reset_token
        user.reset_token_expiry = datetime.utcnow() + timedelta(hours=1)
        db.session.commit()
        
        reset_url = url_for('reset_password_token', token=reset_token, _external=True)
        send_notification(
            user.id,
            'Password Reset Request',
            f'Click the following link to reset your password: {reset_url}\nThis link will expire in 1 hour.',
            'email'
        )
        
        flash('Password reset instructions have been sent to your email')
        return redirect(url_for('login'))
    
    return render_template('forgot_password.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password_token(token):
    user = User.query.filter_by(reset_token=token).first()
    
    if not user or not user.reset_token_expiry or user.reset_token_expiry < datetime.utcnow():
        flash('Invalid or expired password reset link')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if not new_password or not confirm_password:
            flash('Please fill in all fields')
            return redirect(url_for('reset_password_token', token=token))
        
        if new_password != confirm_password:
            flash('Passwords do not match')
            return redirect(url_for('reset_password_token', token=token))
        
        if len(new_password) < 6:
            flash('Password must be at least 6 characters long')
            return redirect(url_for('reset_password_token', token=token))
        
        try:
            user.password = generate_password_hash(new_password)
            user.reset_token = None
            user.reset_token_expiry = None
            db.session.commit()
            flash('Password has been reset successfully. Please login with your new password.')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error resetting password: {str(e)}')
            return redirect(url_for('reset_password_token', token=token))
    
    return render_template('reset_password_token.html')

@app.route('/submit_review/<int:event_id>', methods=['POST'])
@login_required
def submit_review(event_id):
    if current_user.role != 'student':
        flash('Only students can submit reviews')
        return redirect(url_for('home'))
    
    try:
        event = Event.query.get_or_404(event_id)
        booking = Booking.query.filter_by(
            user_id=current_user.id,
            event_id=event_id
        ).first()
        
        if not booking:
            flash('You can only review events you have booked')
            return redirect(url_for('profile'))
            
        existing_review = Review.query.filter_by(
            user_id=current_user.id,
            event_id=event_id
        ).first()
        
        if existing_review:
            flash('You have already reviewed this event')
            return redirect(url_for('profile'))
        
        rating = request.form.get('rating')
        review_text = request.form.get('review_text')
        
        if not rating or not rating.isdigit() or int(rating) < 1 or int(rating) > 5:
            flash('Please provide a valid rating (1-5 stars)')
            return redirect(url_for('profile'))
        
        review = Review(
            user_id=current_user.id,
            event_id=event_id,
            rating=int(rating),
            review_text=review_text
        )
        
        db.session.add(review)
        db.session.commit()
        
        flash('Review submitted successfully!')
        return redirect(url_for('profile'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error submitting review: {str(e)}')
        return redirect(url_for('profile'))

@app.route('/event_reviews/<int:event_id>')
def event_reviews(event_id):
    event = Event.query.get_or_404(event_id)
    reviews = Review.query.filter_by(event_id=event_id).order_by(Review.created_at.desc()).all()
    
    avg_rating = db.session.query(db.func.avg(Review.rating)).filter(Review.event_id == event_id).scalar()
    
    return jsonify({
        'reviews': [{
            'username': review.user.username,
            'rating': review.rating,
            'review_text': review.review_text,
            'created_at': review.created_at.strftime('%B %d, %Y')
        } for review in reviews],
        'average_rating': float(avg_rating) if avg_rating else 0,
        'total_reviews': len(reviews)
    })

@app.route('/book_group/<int:event_id>', methods=['GET', 'POST'])
@login_required
def book_group(event_id):
    event = Event.query.get_or_404(event_id)
    
    if not event.is_group_event:
        flash('This event does not support group bookings.', 'error')
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        try:
            group_size = int(request.form.get('group_size'))
            
            if group_size < event.min_group_size or group_size > event.max_group_size:
                flash('Invalid group size.', 'error')
                return redirect(url_for('book_group', event_id=event_id))
            
            if event.remaining_tickets < group_size:
                flash('Not enough tickets available for the group.', 'error')
                return redirect(url_for('book_group', event_id=event_id))
            
            # This part assumes a simple booking model. You might need to adjust
            # based on your actual group booking logic (e.g., creating a GroupBooking model)
            for _ in range(group_size):
                booking = Booking(
                    user_id=current_user.id,
                    event_id=event.id,
                    name=request.form.get('name'), # You might need individual names
                    email=request.form.get('email'),
                    mobile=request.form.get('mobile'),
                    branch=request.form.get('branch'),
                    year=request.form.get('year'),
                    payment_status='succeeded'
                )
                db.session.add(booking)

            event.remaining_tickets -= group_size
            db.session.commit()
            
            flash('Group booking successful!', 'success')
            return redirect(url_for('profile'))
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while processing your booking. Please try again.', 'error')
            return redirect(url_for('book_group', event_id=event_id))
    
    return render_template('group_booking.html', event=event)

# --- Main Execution Block ---
if __name__ == '__main__':
    # The debug flag should be False in a production environment.
    # You can control this with an environment variable.
    is_debug = os.getenv('FLASK_DEBUG', 'True').lower() in ['true', '1', 't']
    app.run(debug=is_debug)
