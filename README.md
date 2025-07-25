Encypherist
------------------

Encypherist is a full-featured web application designed for students and event organizers. It provides a collaborative space where organizers can create and manage tech events, workshops, and competitions, and students can discover, book, and participate in them.

✨ Key Features
-------
Dual User Roles: Separate registration and profile management for Students and Organizers.

Event Management: Organizers can create, update, and delete events, including details like group bookings, ticket prices, and availability.

Secure Booking System: Students can securely book events, with a multi-step booking form and ticket generation.

Real-time Messaging: Students and organizers can search for each other and communicate directly through a built-in messaging system.

Admin Dashboard: A comprehensive dashboard for administrators to manage users, approve/reject events, and monitor site activity.

Email Authentication: Secure user registration with email verification for new accounts.

Responsive Design: A modern, mobile-first interface that works seamlessly across all devices.

Dynamic Backgrounds: Creative, animated backgrounds on key pages for an engaging user experience.

🛠️ Tech Stack
----------
Frontend
HTML5

Tailwind CSS: For styling and responsive design.

JavaScript: For client-side interactivity and animations.

Vanta.js: For dynamic, animated backgrounds.

Backend
Python: Core programming language.

Flask: Web framework for building the application.

SQLAlchemy: ORM for database interactions.

PostgreSQL: Relational database for storing data.

Flask-Login: For handling user sessions.

Flask-Mail: For sending confirmation and notification emails.

Flask-Migrate: For managing database schema changes.

Werkzeug: For password hashing and security.

🚀 Getting Started
----------
Follow these instructions to get a local copy of the project up and running for development and testing purposes.

Prerequisites
Python 3.8+

pip (Python package installer)

A PostgreSQL database

Installation
Clone the repository:

git clone https://github.com/your-username/encypherist.git
cd encypherist

Create and activate a virtual environment:

# For Windows
python -m venv .venv
.\.venv\Scripts\activate

# For macOS/Linux
python3 -m venv .venv
source .venv/bin/activate

Install the required packages:
---------------------------
pip install -r requirements.txt

(Note: You will need to create a requirements.txt file by running pip freeze > requirements.txt in your terminal.)

Set up your environment variables:
Create a file named .env in the root of your project and add the following variables. Replace the placeholder values with your actual credentials.

SECRET_KEY='a_very_secret_and_secure_key'
DATABASE_URL='postgresql://USER:PASSWORD@HOST:PORT/DATABASE'

# Email Configuration (for registration and notifications)
MAIL_SERVER='smtp.gmail.com'
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME='your-email@gmail.com'
MAIL_PASSWORD='your-gmail-app-password' 

Set up the database:
Run the following commands to apply the database schema:

# Initialize the migrations folder (only needed once)
flask db init

# Create the initial migration script
flask db migrate -m "Initial database schema"

# Apply the migration to the database
flask db upgrade

Run the application:

flask run

🤝 Contributing
-------------------------
Contributions are what make the open-source community such an amazing place to learn, inspire, and create. Any contributions you make are greatly appreciated.

Fork the Project

Create your Feature Branch (git checkout -b feature/AmazingFeature)

Commit your Changes (git commit -m 'Add some AmazingFeature')

Push to the Branch (git push origin feature/AmazingFeature)

Open a Pull Request

📄 License
----------------
This project is open source...
