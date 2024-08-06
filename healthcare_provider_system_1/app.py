import os
import random
import smtplib
from pymongo import MongoClient
from dotenv import load_dotenv
from email.mime.text import MIMEText
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import requests
import string

app = Flask(__name__)
app.secret_key = os.urandom(24)

load_dotenv()

client = MongoClient(os.getenv('MONGO_URI'))
db = client[os.getenv('DB_NAME')]
healthcare_provider_collection = db['healthcare_provider']
users_collection = db['user']
staffs_collection = db['staff']
patients_collection = db['patient']
transfer_request_sent_collection = db['transfer_request_sent']
transfer_request_received_collection = db['transfer_request_received']

REQUEST_SENT = 0
REQUEST_RECEIVED = 1
REQUEST_APPROVED = 2
PATIENT_DATA_TRANSFERRED = 3
PATIENT_DATA_RECEIVED = 4

request_statuses = {
    REQUEST_SENT: "Request Sent",
    REQUEST_RECEIVED: "Request Received",
    REQUEST_APPROVED: "Request Approved",
    PATIENT_DATA_TRANSFERRED: "Patient Data Transferred",
    PATIENT_DATA_RECEIVED: "Patient Data Received"
}

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

def get_provider_name(provider_id):
    try:
        response = requests.get(f'{os.getenv('GHS_HEALTHCARE_PROVIDER_URL')}/{provider_id}')
        if response.status_code == 200:
            provider_data = response.json()
            return provider_data['healthcare_provider_name']
        else:
            return "Unknown Provider"
    except Exception as e:
        return "Unknown Provider"

def get_global_healthcare_providers_details():
    try:
        response = requests.get(os.getenv('GHS_ALL_HEALTHCARE_PROVIDER_URL'))
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": "Failed to fetch data from API"}
    except Exception as e:
        return {"error": str(e)}

def get_healthcare_providers_list_based_on_country(healthcare_providers_list):
    country_based_providers = {}
    for healthcare_provider in healthcare_providers_list:
        country = healthcare_provider['address']['country']
        if country not in country_based_providers:
            country_based_providers[country] = []
        country_based_providers[country].append(healthcare_provider)
    return country_based_providers
    
def find_patient_by_first_name(first_name, last_name, date_of_birth, house_number, post_code, country):
    formatted_first_name = first_name.title()
    formatted_last_name = last_name.title()
    
    patients_with_same_first_name = patients_collection.find({'first_name': formatted_first_name})
    
    for patient in patients_with_same_first_name:
        patient_dob = patient.get('date_of_birth')
        if patient_dob:
            try:
                patient_dob_date = datetime.strptime(patient_dob, '%Y-%m-%dT%H:%M:%S.%f').date()
            except ValueError:
                patient_dob_date = datetime.strptime(patient_dob, '%Y-%m-%d').date()
            
            try:
                given_dob_date = datetime.strptime(date_of_birth, '%Y-%m-%dT%H:%M:%S.%f').date()
            except ValueError:
                given_dob_date = datetime.strptime(date_of_birth, '%Y-%m-%d').date()
        else:
            continue
        
        patient_post_code = patient.get('address', {}).get('post_code', '').replace(' ', '')
        given_post_code = post_code.replace(' ', '')
        
        if (
            patient.get('last_name') == formatted_last_name and
            patient_dob_date == given_dob_date and
            patient.get('address', {}).get('house_number_post_box_number') == house_number and
            patient_post_code == given_post_code and
            patient.get('address', {}).get('country') == country
        ):
            return patient
    
    return None

def generate_strong_password(length=12):
    characters = string.ascii_letters + string.digits + string.punctuation
    password = ''.join(random.choices(characters, k=length))
    return password

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email_address = request.form['email_address']
        password = request.form['password']

        user = users_collection.find_one({'email_address': email_address}, {'_id': 0})

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

        user = users_collection.find_one({'email_address': email_address}, {'_id': 0})
        if user:
            error = 'User already registered. Please login.'
            return render_template('register.html', error=error)

        last_user = users_collection.find_one(sort=[("user_id", -1)])
        new_user_id = last_user['user_id'] + 1 if last_user else 1

        last_patient = patients_collection.find_one(sort=[("patient_id", -1)])
        new_patient_id = last_patient['patient_id'] + 1 if last_patient else 1

        healthcare_provider = healthcare_provider_collection.find_one(sort=[("healthcare_provider_id", -1)])
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

    user = users_collection.find_one({'email_address': email_address}, {'_id': 0})
    if not user:
        return redirect(url_for('login'))

    if user['role'] == 'Patient':
        return redirect(url_for('patient_home'))
    elif user['role'] == 'Staff':
        return redirect(url_for('staff_home'))
    else:
        return redirect(url_for('login'))

@app.route('/patient/home', methods=['GET'])
def patient_home():
    email_address = session.get('email')
    user = users_collection.find_one({'email_address': email_address}, {'_id': 0})
    if not user or user['role'] != 'Patient':
        return redirect(url_for('login'))

    patient = patients_collection.find_one({'user_id': user['user_id']})
    consultations = patient['consultation']

    for consultation in consultations:
        staff_id = consultation.get('staff_id')
        staff_member = staffs_collection.find_one({'staff_id': staff_id}, {'_id': 0})

        if staff_member:
            doctor_name = f"{staff_member['first_name']} {staff_member['last_name']}"
            consultation['doctor_name'] = doctor_name

    user_info = {
        'email_address': user['email_address'],
        'role': user['role'],
        'patient_id': patient['patient_id'],
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

    return render_template('patient_home.html', user_info=user_info, request_statuses=request_statuses)

@app.route('/staff/home', methods=['GET'])
def staff_home():
    email_address = session.get('email')
    user = users_collection.find_one({'email_address': email_address}, {'_id': 0})
    if not user or user['role'] != 'Staff':
        return redirect(url_for('login'))

    staff = staffs_collection.find_one({'user_id': user['user_id']}, {'_id': 0})
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
        user_info['specialization'] = staff['specialization']
        user_info['consultation_hours'] = staff['consultation_hours']

    patients = list(patients_collection.find({},{'_id': 0}))
    patients_info = []

    for patient in patients:
        consultations = patient['consultation']

        for consultation in consultations:
            staff_id = consultation.get('staff_id')
            staff_member = staffs_collection.find_one({'staff_id': staff_id}, {'_id': 0})

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

    healthcare_providers_list = get_global_healthcare_providers_details()
    global_healthcare_providers_details = get_healthcare_providers_list_based_on_country(healthcare_providers_list)

    return render_template('staff_home.html', user_info=user_info, patients_info=patients_info, global_healthcare_providers_details=global_healthcare_providers_details, request_statuses=request_statuses)
    
@app.route('/staff/data/patient/transfer/request/sent', methods=['POST'])
def patient_data_transfer_request_sent():
    data = request.json

    country = data.get('country')
    health_provider_to_id = int(data.get('healthcare_provider_id'))
    first_name = data.get('first_name')
    last_name = data.get('last_name')
    date_of_birth = data.get('date_of_birth')
    house_number = data.get('house_number')
    post_code = data.get('post_code')

    last_transfer_request_sent = transfer_request_sent_collection.find_one(sort=[("user_id", -1)])
    new_transfer_request_id = last_transfer_request_sent['transfer_request_id'] + 1 if last_transfer_request_sent else 1

    healthcare_provider = healthcare_provider_collection.find_one(sort=[("healthcare_provider_id", -1)])
    healthcare_provider_from_id = int(healthcare_provider['healthcare_provider_id']) if healthcare_provider else 1

    transfer_request = {
        'transfer_request_id' : new_transfer_request_id,
        'request_from_healthcare_provider_id' : healthcare_provider_from_id,
        'request_to_healthcare_provider_id' : health_provider_to_id,
        'request_type' : REQUEST_SENT,
        "patient_info": {
            'first_name' : first_name,
            'last_name' : last_name,
            'date_of_birth' : date_of_birth,
            'address' : {
                'house_number' : house_number,
                'post_code' : post_code,
                'country' : country
            }
        },
        'request_status' : REQUEST_SENT
    }

    healthcare_providers_list = get_global_healthcare_providers_details()

    healthcare_provider_url = None
    for healthcare_provider in healthcare_providers_list:
        if healthcare_provider['healthcare_provider_id'] == health_provider_to_id:
            web_address = healthcare_provider.get('web_address', {})
            healthcare_provider_url = f"{web_address.get('domain')}{web_address.get('request_endpoint')}"

    transfer_data_request_query = {
        'from_transfer_request_id' : new_transfer_request_id,
        'healthcare_provider_id' : healthcare_provider_from_id,
        'first_name' : first_name,
        'last_name' : last_name,
        'date_of_birth' : date_of_birth,
        'house_number' : house_number,
        'post_code' : post_code,
        'country' : country
    }

    response = requests.post(healthcare_provider_url, json=transfer_data_request_query)
    if response.status_code == 200:
        print('Request sent successfully')
        print(response.json())
    else:
        print(f'Failed to sent request: {response.status_code}')
        print(response.text)

    transfer_request_sent_collection.insert_one(transfer_request)

    return jsonify({"message": "Request sent successfully"}), 200

@app.route('/staff/data/patient/transfer/request/received', methods=['POST'])
def patient_data_transfer_request_received():
    data = request.json

    from_transfer_request_id = int(data.get('from_transfer_request_id'))
    country = data.get('country')
    healthcare_provider_from_id = int(data.get('healthcare_provider_id'))
    first_name = data.get('first_name')
    last_name = data.get('last_name')
    date_of_birth = data.get('date_of_birth')
    house_number = data.get('house_number')
    post_code = data.get('post_code')

    last_transfer_request_received = transfer_request_received_collection.find_one(sort=[("user_id", -1)])
    new_transfer_request_id = last_transfer_request_received['transfer_request_id'] + 1 if last_transfer_request_received else 1

    healthcare_provider = healthcare_provider_collection.find_one(sort=[("healthcare_provider_id", -1)])
    health_provider_to_id = int(healthcare_provider['healthcare_provider_id']) if healthcare_provider else 1

    patient = find_patient_by_first_name(first_name, last_name, date_of_birth, house_number, post_code, country)

    transfer_request = {
        'transfer_request_id' : new_transfer_request_id,
        'from_transfer_request_id' : from_transfer_request_id,
        'request_from_healthcare_provider_id' : healthcare_provider_from_id,
        'request_to_healthcare_provider_id' : health_provider_to_id,
        'request_type' : REQUEST_RECEIVED,
        "patient_id": patient.get('patient_id'),
        'request_status' : REQUEST_RECEIVED
    }

    transfer_request_received_collection.insert_one(transfer_request)

    return jsonify({"message": "Request received successfully"}), 200

@app.route('/staff/transfer/request/sent/list', methods=['GET'])
def patient_data_transfer_request_sent_list():

    transfer_requests_sent = list(transfer_request_sent_collection.find({},{'_id': 0}))

    for request in transfer_requests_sent:
        request['patient_info']['date_of_birth'] = format_date_of_birth(request['patient_info']['date_of_birth'])
        request['from_provider_name'] = get_provider_name(request['request_from_healthcare_provider_id'])
        request['to_provider_name'] = get_provider_name(request['request_to_healthcare_provider_id'])

    return jsonify(transfer_requests_sent), 200

@app.route('/staff/transfer/request/received/list', methods=['GET'])
def patient_data_transfer_request_received_list():

    transfer_requests_received = list(transfer_request_received_collection.find({},{'_id': 0}))

    for request in transfer_requests_received:
        patient = patients_collection.find_one({'patient_id': request['patient_id']})
        request['patient_info'] = {
            'first_name' : patient.get('first_name'),
            'last_name' : patient.get('last_name'),
            'date_of_birth' : format_date_of_birth(patient.get('date_of_birth')),
            'address' : patient.get('address')
        }
        request['from_provider_name'] = get_provider_name(request['request_from_healthcare_provider_id'])
        request['to_provider_name'] = get_provider_name(request['request_to_healthcare_provider_id'])

    return jsonify(transfer_requests_received), 200

@app.route('/patient/transfer/request/received/list/<patient_id>', methods=['GET'])
def patient_data_transfer_request_received_list_endpoint_for_patient(patient_id):

    transfer_requests_received = list(transfer_request_received_collection.find({'patient_id': int(patient_id)},{'_id': 0}))

    for request in transfer_requests_received:
        request['from_provider_name'] = get_provider_name(request['request_from_healthcare_provider_id'])
        request['to_provider_name'] = get_provider_name(request['request_to_healthcare_provider_id'])

    return jsonify(transfer_requests_received), 200

@app.route('/patient/transfer/request/approve/<transfer_request_id>', methods=['POST'])
def patient_transfer_request_approve(transfer_request_id):

    transfer_request_id = int(transfer_request_id)

    if transfer_request_id is None:
        return jsonify({"error": "Invalid Request Id"}), 400
    
    transfer_request = transfer_request_received_collection.find_one({'transfer_request_id': transfer_request_id})
    
    if not transfer_request:
        return jsonify({"error": "Request Id not found"}), 404

    transfer_request_received_collection.update_one(
        {'transfer_request_id': transfer_request_id},
        {'$set': {'request_status': REQUEST_APPROVED}}
    )
    
    return jsonify({"message": "Request approved successfully"}), 200

@app.route('/staff/patient/data/transfer/send/<transfer_request_id>', methods=['GET'])
def patient_data_transfer_send(transfer_request_id):

    transfer_request_id = int(transfer_request_id)

    if transfer_request_id is None:
        return jsonify({"error": "Invalid Request Id"}), 400
    
    transfer_request = transfer_request_received_collection.find_one({'transfer_request_id': transfer_request_id}, {'_id': 0})

    patient_id = int(transfer_request.get('patient_id'))
    from_transfer_request_id = int(transfer_request.get('from_transfer_request_id'))

    patient = patients_collection.find_one({'patient_id': patient_id}, {'_id': 0})
    user = users_collection.find_one({'user_id' : patient['user_id']}, {'_id': 0})
    
    patient['from_transfer_request_id'] = from_transfer_request_id
    patient['email_address'] = user['email_address']
    patient['original_healthcare_provider_id'] = patient['healthcare_provider_id'] 
    del patient['patient_id']
    del patient['user_id']
    del patient['healthcare_provider_id']

    if not patient:
        return jsonify({"error": "Patient not found"}), 404

    for consultation in patient.get('consultation', []):
        staff_id = consultation.get('staff_id')
        if staff_id:
            staff = staffs_collection.find_one({'staff_id': staff_id}, {'first_name': 1, 'last_name': 1, '_id': 0})
            if staff:
                staff_name = f"{staff['first_name']} {staff['last_name']}"
            else:
                staff_name = "Unknown Staff"
            consultation['staff_name'] = staff_name
            del consultation['staff_id']

    healthcare_providers_list = get_global_healthcare_providers_details()
    request_from_healthcare_provider_id = transfer_request.get('request_from_healthcare_provider_id')

    healthcare_provider_url = None
    for healthcare_provider in healthcare_providers_list:
        if healthcare_provider['healthcare_provider_id'] == request_from_healthcare_provider_id:
            web_address = healthcare_provider.get('web_address', {})
            healthcare_provider_url = f"{web_address.get('domain')}{web_address.get('transfer_endpoint')}"

    response = requests.post(healthcare_provider_url, json=patient)
    if response.status_code == 200:
        print('Request sent successfully')
        print(response.json())
    else:
        print(f'Failed to sent request: {response.status_code}')
        print(response.text)

    transfer_request_received_collection.update_one(
        {'transfer_request_id': transfer_request_id},
        {'$set': {'request_status': PATIENT_DATA_TRANSFERRED}}
    )
    return jsonify({"message": "Patient data sent successfully", "data": patient}), 200

@app.route('/staff/patient/data/transfer/receive', methods=['POST'])
def patient_data_transfer_receive():
    patient_data = request.json

    last_patient = patients_collection.find_one(sort=[("patient_id", -1)])
    new_patient_id = last_patient['patient_id'] + 1 if last_patient else 1

    healthcare_provider = healthcare_provider_collection.find_one(sort=[("healthcare_provider_id", -1)])
    healthcare_provider_id = healthcare_provider['healthcare_provider_id'] if last_patient else 1

    from_transfer_request_id = patient_data['from_transfer_request_id']

    patient_data['patient_id'] = new_patient_id
    patient_data['healthcare_provider_id'] = healthcare_provider_id

    email_address = patient_data['email_address']
    del patient_data['email_address']

    last_user = users_collection.find_one(sort=[("user_id", -1)])
    new_user_id = last_user['user_id'] + 1 if last_user else 1

    users_collection.insert_one({
        'user_id': new_user_id,
        'email_address': email_address,
        'password': generate_strong_password(),
        'role': os.getenv('ROLE_PATIENT')
    })

    patient_data['user_id'] = new_user_id

    patients_collection.insert_one(patient_data)

     transfer_request_sent_collection.update_one(
        {'transfer_request_id': from_transfer_request_id},
        {'$set': {'request_status': PATIENT_DATA_RECEIVED}}
    )

    return jsonify({"message": "Patient data received successfully"}), 200

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, port=os.getenv('PORT'))
