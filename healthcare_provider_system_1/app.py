import os
import random
import smtplib
from pymongo import MongoClient
from dotenv import load_dotenv
from email.mime.text import MIMEText
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = os.urandom(24)

load_dotenv()

client = MongoClient(os.getenv('MONGO_URI'))
db = client[os.getenv('DB_NAME')]
healthcare_provider_collection = db['healthcare_provider']
users_collection = db['user']
staffs_collection = db['staff']
patients_collection = db['patient']

def generate_otp():
    return str(random.randint(100000, 999999))

def send_otp_email(otp, recipient_email):
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    sender_email = os.getenv('EMAIL_ADDRESS')
    sender_password = os.getenv('EMAIL_PASSWORD')
    
    subject = "Your OTP Code"
    body = f"Your OTP code is: {otp}"
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = recipient_email
    
    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipient_email, msg.as_string())

def calculate_age(date_of_birth):
    birth_date = datetime.strptime(date_of_birth, "%Y-%m-%d")
    today = datetime.today()
    age = today.year - birth_date.year
    if today.month < birth_date.month or (today.month == birth_date.month and today.day < birth_date.day):
        age -= 1
    return age

def format_date_of_birth(date_of_birth_str):
    date_of_birth = datetime.fromisoformat(date_of_birth_str)
    formatted_date_of_birth = date_of_birth.strftime('%d %B %Y')
    return formatted_date_of_birth

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email_address = request.form['email_address']
        password = request.form['password']

        user = users_collection.find_one({'email_address': email_address})

        if user and user['password'] == password:
            otp = generate_otp()
            session['otp'] = otp
            session['email'] = email_address
            session['role'] = user['role']
            send_otp_email(otp, email_address)
            return redirect(url_for('mfa'))
        else:
            error = 'Invalid Credentials. Please try again.'
            return render_template('login.html', error=error)
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email_address = request.form['email_address']
        password = request.form['password']
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        date_of_birth = request.form['date_of_birth']
        gender = request.form['gender']
        house_number_post_box_number = request.form['house_number_post_box_number']
        post_code = request.form['post_code']

        user = users_collection.find_one({'email_address': email_address})
        if user:
            error = 'User already registered. Please login.'
            return render_template('register.html', error=error)

        last_user = users_collection.find_one(sort=[("user_id", -1)])
        new_user_id = last_user['user_id'] + 1 if last_user else 1

        last_patient = patients_collection.find_one(sort=[("patient_id", -1)])
        new_patient_id = last_patient['patient_id'] + 1 if last_patient else 1

        healthcare_provider = healthcare_provider.find_one(sort=[("healthcare_provider_id", -1)])
        healthcare_provider_id = healthcare_provider['healthcare_provider_id'] if last_patient else 1

        users_collection.insert_one({
            'user_id': new_user_id,
            'email_address': email_address,
            'password': password,
            'role': os.getenv('ROLE_PATIENT')
        })

        patients_collection.insert_one({
            'patient_id': new_patient_id,
            'user_id': new_user_id,
            'healthcare_provider_id': healthcare_provider_id,
            'first_name': first_name,
            'last_name': last_name,
            'date_of_birth': date_of_birth,
            'gender': gender,
            'age': calculate_age(date_of_birth),
            'address' : {
                'house_number_post_box_number': house_number_post_box_number,
                'post_code': post_code,
                'country': healthcare_provider['country']
            },
            'consultation': [],
            'diagnosis': [],
            'medication': []
        })

        otp = generate_otp()
        session['otp'] = otp
        session['email'] = email_address
        send_otp_email(otp, email_address)

        return redirect(url_for('mfa'))
    return render_template('register.html')

@app.route('/mfa', methods=['GET', 'POST'])
def mfa():
    if request.method == 'POST':
        mfa_code = request.form['mfa_code']
        if 'otp' in session and session['otp'] == mfa_code:
            session.pop('otp', None)
            session['logged_in'] = True
            return redirect(url_for('home'))
        else:
            error = 'Invalid MFA code. Please try again.'
            return render_template('mfa.html', error=error)
    
    return render_template('mfa.html', email_address=session.get('email'))

@app.route('/home', methods=['GET'])
def home():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    email_address = session.get('email')
    if not email_address:
        return redirect(url_for('login'))
    
    user = users_collection.find_one({'email_address': email_address})
    if not user:
        return redirect(url_for('login'))

    if user['role'] == 'Patient':
    
        patient = patients_collection.find_one({'user_id': user['user_id']})

        consultations = patient['consultation']

        for consultation in consultations:
            staff_id = consultation.get('staff_id')
            staff_member = staffs_collection.find_one({'staff_id': staff_id})

            if staff_member:
                doctor_name = f"{staff_member['first_name']} {staff_member['last_name']}"
                consultation['doctor_name'] = doctor_name
    
        user_info = {
            'email_address': user['email_address'],
            'role': user['role'],
            'first_name': patient['first_name'],
            'last_name': patient['last_name'],
            'date_of_birth': format_date_of_birth(patient['date_of_birth']),
            'age': patient['age'],
            'gender': patient['gender'],
            'house_number_post_box_number': patient['address']['house_number_post_box_number'],
            'post_code': patient['address']['post_code'],
            'country': patient['address']['country'],
            'consultation': consultations,
            'diagnosis': patient['diagnosis'],
            'medication': patient['medication']
        }
    
        return render_template('patient_home.html', user_info=user_info)
    
    elif user['role'] == 'Staff':

        staff = staffs_collection.find_one({'user_id': user['user_id']})
        role = staff['role']
        user_info = {
            'email_address': user['email_address'],
            'role': user['role'],
            'first_name': staff['first_name'],
            'last_name': staff['last_name'],
            'role': role,
            'house_number_post_box_number': staff['address']['house_number_post_box_number'],
            'post_code': staff['address']['post_code'],
            'country': staff['address']['country'],
            'years_of_experience': staff['years_of_experience'],
            'qualifications': staff['qualifications']
        }

        if role == 'Doctor':
            user_info.specialization = staff['specialization']
            user_info.consultation_hours = staff['consultation_hours']
    
        patients = list(patients_collection.find())
        patients_info = []
    
        for patient in patients:

            consultations = patient['consultation']

            for consultation in consultations:
                staff_id = consultation.get('staff_id')
                staff_member = staffs_collection.find_one({'staff_id': staff_id})

                if staff_member:
                    doctor_name = f"{staff_member['first_name']} {staff_member['last_name']}"
                    consultation['doctor_name'] = doctor_name


            patient_info = {
                'first_name': patient['first_name'],
                'last_name': patient['last_name'],
                'date_of_birth': format_date_of_birth(patient['date_of_birth']),
                'age': patient['age'],
                'gender': patient['gender'],
                'house_number_post_box_number': patient['address']['house_number_post_box_number'],
                'post_code': patient['address']['post_code'],
                'country': patient['address']['country'],
                'consultation': consultations,
                'diagnosis': patient['diagnosis'],
                'medication': patient['medication']
            }

            patients_info.append(patient_info)

        return render_template('staff_home.html', user_info=user_info, patients_info=patients_info)
    
    else:
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
