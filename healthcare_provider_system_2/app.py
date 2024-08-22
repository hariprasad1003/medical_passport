import os
import random
import smtplib
from pymongo import MongoClient
from dotenv import load_dotenv
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, abort
import requests
import string
import aes_encryption
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import jwt
from functools import wraps
from markupsafe import escape
from werkzeug.security import generate_password_hash, check_password_hash
from blockchain import Blockchain
from bson import ObjectId
import rsa_encryption
import base64
import hashlib
import json

app = Flask(__name__)
app.secret_key = os.urandom(24)


app.config.update(
    SESSION_COOKIE_SECURE=False,
    SESSION_COOKIE_HTTPONLY=True,
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
    SESSION_COOKIE_SAMESITE='Lax'
)

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["10 per minute", "100 per hour"]
)
limiter.init_app(app)

load_dotenv()

app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')

KEK_COMMON = os.getenv('KEK_COMMON')
kek_common_bytes = base64.b64decode(KEK_COMMON)

client = MongoClient(os.getenv('MONGO_URI'))
db = client[os.getenv('DB_NAME')]
healthcare_provider_collection = db['healthcare_provider']
users_collection = db['user']
staffs_collection = db['staff']
patients_collection = db['patient']
transfer_request_sent_collection = db['transfer_request_sent']
transfer_request_received_collection = db['transfer_request_received']
blockchain_collection = db['blockchain']

blockchain = Blockchain(blockchain_collection)

REQUEST_SENT = 0
REQUEST_RECEIVED = 1
REQUEST_APPROVED = 2
PATIENT_DATA_TRANSFERRED = 3
PATIENT_DATA_RECEIVED = 4
REQUEST_RECEIVED_PATIENT_NOT_FOUND = -1

request_statuses = {
    REQUEST_SENT: "Request Sent",
    REQUEST_RECEIVED: "Request Received",
    REQUEST_APPROVED: "Request Approved",
    PATIENT_DATA_TRANSFERRED: "Patient Data Transferred",
    PATIENT_DATA_RECEIVED: "Patient Data Received",
    REQUEST_RECEIVED_PATIENT_NOT_FOUND: "Request Received but Patient Data Not Found"
}

PATIENT=0
STAFF=1
ADMIN=0
DOCTOR=1

ACCESS_TOKEN = None
ACCESS_TOKEN_TIME = None

ROLE_PERMISSIONS = {
    PATIENT: {
        'allowed_endpoints': [
            'patient_home',
            'patient_data_transfer_request_received_list_endpoint_for_patient',
            'patient_transfer_request_approve'
        ]
    },
    STAFF: {
        'allowed_endpoints': [
            'staff_home',
            'get_patients',
            'patient_data_transfer_request_sent',
            'patient_data_transfer_request_received',
            'patient_data_transfer_request_sent_list',
            'patient_data_transfer_request_received_list',
            'patient_data_transfer_send',
            'patient_data_transfer_receive',
            'transfer_patient_data_integrity_check'
        ]
    }
}

healthcare_providers_list = []

REQUEST_ENDPOINT = 'request_endpoint'
TRANSFER_ENDPOINT = 'transfer_endpoint'
REQUEST_UPDATE_ENDPOINT = 'request_update_endpoint'
INTEGRITY_ENDPOINT = 'integrity_endpoint'
KEY_ENDPOINT = 'key_endpoint'


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

def get_access_token_ghs():
    global ACCESS_TOKEN, ACCESS_TOKEN_TIME
    
    if ACCESS_TOKEN and ACCESS_TOKEN_TIME:
        elapsed_time = datetime.now() - ACCESS_TOKEN_TIME
        if elapsed_time < timedelta(minutes=30):
            return 200, ACCESS_TOKEN
    
    healthcare_provider = healthcare_provider_collection.find_one(sort=[("healthcare_provider_id", -1)])
    CLIENT_ID = os.getenv('GHS_CLIENT_ID')
    CLIENT_TOKEN = os.getenv('GHS_CLIENT_TOKEN')
    ACCESS_TOKEN_URL = f"{os.getenv('GHS_HEALTHCARE_PROVIDER_ACCESS_TOKEN_URL')}/{healthcare_provider['healthcare_provider_id']}"
    
    headers = {
        'Client-Id': CLIENT_ID,
        'Client-Token': CLIENT_TOKEN
    }
    
    try:
        response = requests.get(ACCESS_TOKEN_URL, headers=headers)
        if response.status_code == 200:
            data = response.json()
            ACCESS_TOKEN = data['access_token']
            ACCESS_TOKEN_TIME = datetime.now()
            return response.status_code, ACCESS_TOKEN
        else:
            return response.status_code, "Error: Failed to get the access token"
    except Exception as e:
        return 500, f"Error: {str(e)}"

def get_provider_name(provider_id):
    status_code, access_token = get_access_token_ghs()
    if status_code != 200:
        return "Unable to retrieve access token"

    headers = {
        'Authorization': f'Bearer {access_token}'
    }

    try:
        response = requests.get(f'{os.getenv('GHS_HEALTHCARE_PROVIDER_URL')}/{provider_id}', headers=headers)
        if response.status_code == 200:
            provider_data = response.json()
            return provider_data['healthcare_provider_name']
        else:
            return "Unknown Provider"
    except Exception as e:
        return "Unknown Provider"

def get_global_healthcare_providers_details():
    global healthcare_providers_list
    if len(healthcare_providers_list) > 0:
        return healthcare_providers_list

    status_code, access_token = get_access_token_ghs()
    if status_code != 200:
        return "Unable to retrieve access token"

    headers = {
        'Authorization': f'Bearer {access_token}'
    }

    try:
        response = requests.get(os.getenv('GHS_ALL_HEALTHCARE_PROVIDER_URL'), headers=headers)
        if response.status_code == 200:
            healthcare_providers_list = response.json()
            return healthcare_providers_list
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

def get_healthcare_provider_url(healthcare_provider_id, url_type):
    healthcare_providers_list = get_global_healthcare_providers_details()

    healthcare_provider_url = None
    for healthcare_provider in healthcare_providers_list:
        if int(healthcare_provider['healthcare_provider_id']) == int(healthcare_provider_id):
            web_address = healthcare_provider.get('web_address', {})
            healthcare_provider_url = f"{web_address.get('domain')}{web_address.get(url_type)}"

    return healthcare_provider_url    

def find_patient_by_first_name(first_name, last_name, date_of_birth, house_number, post_code, country):
    formatted_first_name = first_name.title()
    formatted_last_name = last_name.title()
    
    patients = patients_collection.find()
    
    for patient in patients:
        patient = aes_encryption.decrypt_collection_document(patient)
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
            patient.get('first_name') == formatted_first_name and
            patient.get('last_name') == formatted_last_name and
            patient_dob_date == given_dob_date and
            patient.get('address', {}).get('house_number') == house_number and
            patient_post_code == given_post_code and
            patient.get('address', {}).get('country') == country
        ):
            return patient
    
    return None

def generate_strong_password(length=12):
    characters = string.ascii_letters + string.digits + string.punctuation
    password = ''.join(random.choices(characters, k=length))
    return password

def create_token(email_address):
    token = jwt.encode({
        'email_address': email_address,
        'exp': datetime.utcnow() + timedelta(minutes=30)
    }, app.config['JWT_SECRET_KEY'], algorithm='HS256')
    return token

def sanitize_input(value):
    if isinstance(value, dict):
        return {k: sanitize_input(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [sanitize_input(item) for item in value]
    elif isinstance(value, str):
        return escape(value)
    else:
        return value

def add_transaction_to_blockchain(transfer_request):
    blockchain.new_transaction(transfer_request)

    last_proof = blockchain.last_block['proof']
    proof = blockchain.proof_of_work(last_proof)

    previous_hash = blockchain.hash(blockchain.last_block)
    block = blockchain.new_block(proof, previous_hash)

def token_required_internal_call(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token_from_request = request.headers.get('Authorization')
        token_from_session = session.get('access_token')

        if not token_from_request and not token_from_session:
            return jsonify({'message': 'Token is missing!'}), 403


        if token_from_request:
            token_from_request = token_from_request.split(" ")[1]

            if not token_from_session or (token_from_session != token_from_request):
                return jsonify({'message': 'Invalid or expired token!'}), 403

        try:
            if token_from_request:
                data = jwt.decode(token_from_request, app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
            elif token_from_session:
                data = jwt.decode(token_from_session, app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired!'}), 403
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Invalid token!'}), 403

        return f(*args, **kwargs)
    return decorated

def token_required_external_call(f):
    @wraps(f)
    def decorated(*args, **kwargs):

        token_from_request = request.headers.get('Authorization')

        if not token_from_request:
            return jsonify({'message': 'Token is missing!'}), 403

        status_code, access_token = get_access_token_ghs()
        headers = {
            'Authorization': f'Bearer {access_token}'
        }

        data = {
            'access_token': token_from_request.split(" ")[1]
        }

        url = os.getenv('GHS_HEALTHCARE_PROVIDER_VALIDATE_ACCESS_TOKEN_URL')

        response = requests.post(url, json=data, headers=headers)
        if response.status_code != 200:
            return jsonify({'message': 'Token is invalid or expired!'}), 403

        return f( *args, **kwargs)

    return decorated

def role_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_role = session.get('role')
        if user_role == None:
            abort(403, 'Access denied: No role defined in session.')

        role_info = ROLE_PERMISSIONS.get(user_role, {})

        if request.endpoint not in role_info.get('allowed_endpoints', []):
            abort(403, 'Access denied: Your role does not have permission to access this resource.')

        return f(*args, **kwargs)

    return decorated_function

def encrypt_transfer_data(document):
    private_key, public_key = rsa_encryption.generate_keys()
    encrypted_data = rsa_encryption.encrypt_document(document, public_key)
    encrypted_data = rsa_encryption.encode_to_base64(encrypted_data)
    private_key_pem = rsa_encryption.convert_private_key_to_pem(private_key)
    public_key_pem = rsa_encryption.convert_public_key_to_pem(public_key)

    encrypted_private_pem = aes_encryption.encrypt_dek(private_key_pem, rsa_encryption.kek2_bytes)
    encrypted_public_pem = aes_encryption.encrypt_dek(public_key_pem, rsa_encryption.kek2_bytes)

    return encrypted_data, encrypted_private_pem, encrypted_public_pem

def decrypt_tranfer_data(document, key):
    private_key_bytes = base64.b64decode(key)
    private_key = rsa_encryption.convert_pem_to_private_key(private_key_bytes)
    document = rsa_encryption.decode_from_base64(document)
    decrypted_document = rsa_encryption.decrypt_document(document, private_key)
    return decrypted_document

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email_address = escape(request.form['email_address'])
        password = request.form['password']

        user = users_collection.find_one({'email_address': email_address})
        if user:
            user = aes_encryption.decrypt_collection_document(user)
            if user and user['password'] == password:
                otp = generate_otp()
                session['otp'] = otp
                access_token = create_token(email_address)
                session['access_token'] = access_token
                session['email'] = email_address
                session['role'] = user['role']
                send_otp_email(otp, email_address)
                return redirect(url_for('mfa'))
            else:
                error = 'Invalid Credentials. Please try again.'
                return render_template('login.html', error=error)
        else:
            error = 'Invalid Credentials. Please try again.'
            return render_template('login.html', error=error)
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email_address = escape(request.form['email_address'])
        password = request.form['password']
        first_name = escape(request.form['first_name'])
        last_name = escape(request.form['last_name'])
        date_of_birth = escape(request.form['date_of_birth'])
        gender = escape(request.form['gender'])
        house_number = escape(request.form['house_number'])
        post_code = escape(request.form['post_code'])

        user = users_collection.find_one({'email_address': email_address})
        if user:
            error = 'User already registered. Please login.'
            return render_template('register.html', error=error)

        last_user = users_collection.find_one(sort=[("user_id", -1)])
        new_user_id = last_user['user_id'] + 1 if last_user else 1

        last_patient = patients_collection.find_one(sort=[("patient_id", -1)])
        new_patient_id = last_patient['patient_id'] + 1 if last_patient else 1

        healthcare_provider = healthcare_provider_collection.find_one(sort=[("healthcare_provider_id", -1)])
        healthcare_provider = aes_encryption.decrypt_collection_document(healthcare_provider)
        healthcare_provider_id = healthcare_provider['healthcare_provider_id'] if last_patient else 1

        user = {
            'user_id': new_user_id,
            'email_address': email_address,
            'password': password,
            'role': PATIENT
        }
        user, encrypted_dek = aes_encryption.encrypt_collection_document(user)
        result = users_collection.insert_one(user)
        inserted_id = result.inserted_id
        aes_encryption.insert_encryted_document_key(inserted_id, encrypted_dek)

        patient = {
            'patient_id': new_patient_id,
            'user_id': new_user_id,
            'healthcare_provider_id': healthcare_provider_id,
            'first_name': first_name,
            'last_name': last_name,
            'date_of_birth': date_of_birth,
            'gender': gender,
            'age': str(calculate_age(date_of_birth)),
            'address' : {
                'house_number': house_number,
                'post_code': post_code,
                'country': healthcare_provider['address']['country']
            },
            'consultation': [],
            'diagnosis': [],
            'medication': []
        }
        patient, encrypted_dek = aes_encryption.encrypt_collection_document(patient)
        result = patients_collection.insert_one(patient)
        inserted_id = result.inserted_id
        aes_encryption.insert_encryted_document_key(inserted_id, encrypted_dek)

        otp = generate_otp()
        session['otp'] = otp
        access_token = create_token(email_address)
        session['access_token'] = access_token
        session['email'] = email_address
        session['role'] = PATIENT
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

    if user['role'] == PATIENT:
        return redirect(url_for('patient_home'))
    elif user['role'] == STAFF:
        return redirect(url_for('staff_home'))
    else:
        return redirect(url_for('login'))

@app.route('/patient/home', methods=['GET'])
@token_required_internal_call
@role_required
def patient_home():
    email_address = session.get('email')
    user = users_collection.find_one({'email_address': email_address})
    if not user or user['role'] != PATIENT:
        return redirect(url_for('login'))

    patient = patients_collection.find_one({'user_id': user['user_id']})
    patient = aes_encryption.decrypt_collection_document(patient)
    consultations = patient['consultation']

    for consultation in consultations:
        staff_id = consultation.get('staff_id')
        staff_member = staffs_collection.find_one({'staff_id': staff_id})
        staff_member = aes_encryption.decrypt_collection_document(staff_member)

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
        'house_number': patient['address']['house_number'],
        'post_code': patient['address']['post_code'],
        'country': patient['address']['country'],
        'consultation': consultations,
        'diagnosis': patient['diagnosis'],
        'medication': patient['medication']
    }

    return render_template('patient_home.html', user_info=user_info, access_token=session.get('access_token'), request_statuses=request_statuses)

@app.route('/staff/home', methods=['GET'])
@token_required_internal_call
@role_required
def staff_home():
    email_address = session.get('email')
    user = users_collection.find_one({'email_address': email_address})
    if not user or user['role'] != STAFF:
        return redirect(url_for('login'))

    staff = staffs_collection.find_one({'user_id': user['user_id']})
    staff = aes_encryption.decrypt_collection_document(staff)
    role = staff['role']
    user_info = {
        'email_address': user['email_address'],
        'role': user['role'],
        'first_name': staff['first_name'],
        'last_name': staff['last_name'],
        'role': role,
        'house_number': staff['address']['house_number'],
        'post_code': staff['address']['post_code'],
        'country': staff['address']['country'],
        'years_of_experience': staff['years_of_experience'],
        'qualifications': staff['qualifications']
    }

    if role == DOCTOR:
        user_info['specialization'] = staff['specialization']
        user_info['consultation_hours'] = staff['consultation_hours']

    healthcare_providers_list = get_global_healthcare_providers_details()
    global_healthcare_providers_details = get_healthcare_providers_list_based_on_country(healthcare_providers_list)

    return render_template('staff_home.html', user_info=user_info, access_token=session.get('access_token'),global_healthcare_providers_details=global_healthcare_providers_details, request_statuses=request_statuses)

@app.route('/api/staff/home/patients/list', methods=['GET'])
@token_required_internal_call
@role_required
def get_patients():
    patients = list(patients_collection.find({}))
    patients_info = []

    for patient in patients:
        patient = aes_encryption.decrypt_collection_document(patient)
        consultations = patient.get('consultation', [])
        for consultation in consultations:
            staff_id = consultation.get('staff_id')
            staff_name = consultation.get('staff_name')
            if staff_id:
                staff_member = staffs_collection.find_one({'staff_id': staff_id})
                if staff_member:
                    staff_member = aes_encryption.decrypt_collection_document(staff_member)
                    doctor_name = f"{staff_member['first_name']} {staff_member['last_name']}"
                    consultation['doctor_name'] = doctor_name
            elif staff_name:
                consultation['doctor_name'] = staff_name

        patient_info = {
            'first_name': patient['first_name'],
            'last_name': patient['last_name'],
            'date_of_birth': format_date_of_birth(patient['date_of_birth']),
            'age': patient['age'],
            'gender': patient['gender'],
            'house_number': patient['address']['house_number'],
            'post_code': patient['address']['post_code'],
            'country': patient['address']['country'],
            'consultation': consultations,
            'diagnosis': patient['diagnosis'],
            'medication': patient['medication']
        }
        patients_info.append(patient_info)

    return jsonify(patients_info), 200

@app.route('/api/staff/data/patient/transfer/request/sent', methods=['POST'])
@token_required_internal_call
@role_required
def patient_data_transfer_request_sent():
    data = request.json

    country = escape(data.get('country'))
    healthcare_provider_to_id = int(escape(data.get('healthcare_provider_id')))
    first_name = escape(data.get('first_name'))
    last_name = escape(data.get('last_name'))
    date_of_birth = escape(data.get('date_of_birth'))
    house_number = escape(data.get('house_number'))
    post_code = escape(data.get('post_code'))

    last_transfer_request_sent = transfer_request_sent_collection.find_one(sort=[("transfer_request_id", -1)])
    new_transfer_request_id = last_transfer_request_sent['transfer_request_id'] + 1 if last_transfer_request_sent else 1

    healthcare_provider = healthcare_provider_collection.find_one(sort=[("healthcare_provider_id", -1)])
    healthcare_provider_from_id = int(healthcare_provider['healthcare_provider_id']) if healthcare_provider else 1

    transfer_request = {
        'transfer_request_id' : new_transfer_request_id,
        'request_from_healthcare_provider_id' : healthcare_provider_from_id,
        'request_to_healthcare_provider_id' : healthcare_provider_to_id,
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

    transfer_request, encrypted_dek = aes_encryption.encrypt_collection_document(transfer_request)
    result = transfer_request_sent_collection.insert_one(transfer_request)
    inserted_id = result.inserted_id
    aes_encryption.insert_encryted_document_key(inserted_id, encrypted_dek)

    add_transaction_to_blockchain(transfer_request)

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

    encrypted_data, encrypted_private_pem, encrypted_public_pem = encrypt_transfer_data(transfer_data_request_query)
    rsa_encryption.insert_encryted_document_key(new_transfer_request_id, encrypted_private_pem, encrypted_public_pem)

    healthcare_provider_url = get_healthcare_provider_url(healthcare_provider_to_id, REQUEST_ENDPOINT)
    status_code, access_token = get_access_token_ghs()
    headers = {
        'Authorization': f'Bearer {access_token}'
    }

    response = requests.post(healthcare_provider_url, json=encrypted_data, headers=headers)
    if response.status_code == 200:
        print('Request sent successfully')
        print(response.json())
    else:
        print(f'Failed to sent request: {response.status_code}')
        print(response.text)

    return jsonify({"message": "Request sent successfully"}), 200

@app.route('/api/staff/patient/data/get/key/request/<transfer_request_id>', methods=['GET'])
@token_required_external_call
def patient_data_transfer_request_get_key(transfer_request_id):
    document = rsa_encryption.get_encrypted_document_key(transfer_request_id)

    encrypted_private_pem = document['encrypted_private_key']
    encrypted_public_pem = document['encrypted_public_key']

    decrypted_private_pem = aes_encryption.decrypt_dek(encrypted_private_pem, rsa_encryption.kek2_bytes)
    decrypted_public_pem = aes_encryption.decrypt_dek(encrypted_public_pem, rsa_encryption.kek2_bytes)

    private_key_str = base64.b64encode(decrypted_private_pem).decode('utf-8')

    encrypted_private_key_pem = aes_encryption.encrypt_dek(private_key_str.encode('utf-8'), kek_common_bytes)

    return jsonify({"key": encrypted_private_key_pem}), 200

@app.route('/api/staff/data/patient/transfer/request/received', methods=['POST'])
@token_required_external_call
def patient_data_transfer_request_received():
    data = request.json

    healthcare_provider_from_id = int(escape(data.get('healthcare_provider_id')))
    from_transfer_request_id = int(escape(data.get('from_transfer_request_id')))

    healthcare_provider_url = get_healthcare_provider_url(healthcare_provider_from_id, KEY_ENDPOINT)
    status_code, access_token = get_access_token_ghs()
    headers = {
        'Authorization': f'Bearer {access_token}'
    }

    key = None
    response = requests.get(f'{healthcare_provider_url}/{from_transfer_request_id}', headers=headers)
    if response.status_code == 200:
        print(f'Request key fetched successfully: ')
        response_data = response.json()
        encrypted_key = response_data['key']
        key = aes_encryption.decrypt_dek(encrypted_key, kek_common_bytes)
    else:
        print(f'Failed to sent request: {response.status_code}')
        print(response.text)

    data = decrypt_tranfer_data(data, key)

    first_name = escape(data.get('first_name'))
    last_name = escape(data.get('last_name'))
    date_of_birth = escape(data.get('date_of_birth'))
    house_number = escape(data.get('house_number'))
    post_code = escape(data.get('post_code'))
    country = escape(data.get('country'))

    last_transfer_request_received = transfer_request_received_collection.find_one(sort=[("user_id", -1)])
    new_transfer_request_id = last_transfer_request_received['transfer_request_id'] + 1 if last_transfer_request_received else 1

    healthcare_provider = healthcare_provider_collection.find_one(sort=[("healthcare_provider_id", -1)])
    health_provider_to_id = int(healthcare_provider['healthcare_provider_id']) if healthcare_provider else 1

    patient = find_patient_by_first_name(first_name, last_name, date_of_birth, house_number, post_code, country)

    patient_id = REQUEST_RECEIVED_PATIENT_NOT_FOUND
    request_status = REQUEST_RECEIVED_PATIENT_NOT_FOUND
    if(patient != None and len(patient) > 0):
        patient_id = patient.get('patient_id')
        request_status = REQUEST_RECEIVED

    transfer_request = {
        'transfer_request_id' : new_transfer_request_id,
        'from_transfer_request_id' : from_transfer_request_id,
        'request_from_healthcare_provider_id' : healthcare_provider_from_id,
        'request_to_healthcare_provider_id' : health_provider_to_id,
        'request_type' : REQUEST_RECEIVED,
        "patient_id": patient_id,
        'request_status' : request_status
    }

    if patient_id == REQUEST_RECEIVED_PATIENT_NOT_FOUND:
        patient_info = {
            'first_name' : first_name,
            'last_name' : last_name,
            'date_of_birth' : date_of_birth,
            'address' : {
                'house_number' : house_number,
                'post_code' : post_code,
                'country' : country
            }
        }

        transfer_request["patient_info"] = patient_info

    transfer_request_received_collection.insert_one(transfer_request)

    healthcare_provider_url = get_healthcare_provider_url(healthcare_provider_from_id, REQUEST_UPDATE_ENDPOINT)

    data = {
        'transfer_request_id' : from_transfer_request_id,
        'transfer_request_status' : request_status
    }

    response = requests.post(healthcare_provider_url, json=data, headers=headers)
    if response.status_code == 200:
        print(f'Request status updated successfully: {request_status}')
        print(response.json())
    else:
        print(f'Failed to sent request: {response.status_code}')
        print(response.text)

    if transfer_request and '_id' in transfer_request:
        del transfer_request['_id']

    add_transaction_to_blockchain(transfer_request)

    return jsonify({"message": "Request received successfully"}), 200

@app.route('/api/staff/transfer/request/sent/list', methods=['GET'])
@token_required_internal_call
@role_required
def patient_data_transfer_request_sent_list():

    transfer_requests_sent = list(transfer_request_sent_collection.find({}))

    sanitized_requests = []
    for request in transfer_requests_sent:
        request = aes_encryption.decrypt_collection_document(request)
        del request['_id']
        request['patient_info']['date_of_birth'] = format_date_of_birth(request['patient_info']['date_of_birth'])
        request['from_provider_name'] = get_provider_name(request['request_from_healthcare_provider_id'])
        request['to_provider_name'] = get_provider_name(request['request_to_healthcare_provider_id'])
        sanitized_requests.append(request)

    return jsonify(sanitized_requests), 200

@app.route('/api/staff/transfer/request/received/list', methods=['GET'])
@token_required_internal_call
@role_required
def patient_data_transfer_request_received_list():

    transfer_requests_received = list(transfer_request_received_collection.find({}))

    sanitized_requests = []
    for request in transfer_requests_received:
        patient_id = request['patient_id']
        if patient_id != REQUEST_RECEIVED_PATIENT_NOT_FOUND:
            patient = patients_collection.find_one({'patient_id': patient_id})
            patient = aes_encryption.decrypt_collection_document(patient)
            request['patient_info'] = {
                'first_name' : patient.get('first_name'),
                'last_name' : patient.get('last_name'),
                'date_of_birth' : format_date_of_birth(patient.get('date_of_birth')),
                'address' : patient.get('address')
            }
        del request['_id']
        request['from_provider_name'] = get_provider_name(request['request_from_healthcare_provider_id'])
        request['to_provider_name'] = get_provider_name(request['request_to_healthcare_provider_id'])
        sanitized_requests.append(request)

    return jsonify(sanitized_requests), 200

@app.route('/api/patient/transfer/request/received/list/<patient_id>', methods=['GET'])
@token_required_internal_call
@role_required
def patient_data_transfer_request_received_list_endpoint_for_patient(patient_id):

    transfer_requests_received = list(transfer_request_received_collection.find({'patient_id': int(escape(patient_id))}))

    sanitized_requests = []
    for request in transfer_requests_received:
        request['from_provider_name'] = get_provider_name(request['request_from_healthcare_provider_id'])
        request['to_provider_name'] = get_provider_name(request['request_to_healthcare_provider_id'])
        del request['_id']
        sanitized_requests.append(request)

    return jsonify(sanitized_requests), 200

@app.route('/api/patient/transfer/request/approve/<transfer_request_id>', methods=['POST'])
@token_required_internal_call
@role_required
def patient_transfer_request_approve(transfer_request_id):

    transfer_request_id = int(escape(transfer_request_id))

    if transfer_request_id is None:
        return jsonify({"error": "Invalid Request Id"}), 400
    
    transfer_request = transfer_request_received_collection.find_one({'transfer_request_id': transfer_request_id})
    from_transfer_request_id = transfer_request["from_transfer_request_id"]
    healthcare_provider_from_id = transfer_request["request_from_healthcare_provider_id"]

    if not transfer_request:
        return jsonify({"error": "Request Id not found"}), 404

    updated_document = transfer_request_received_collection.find_one_and_update(
        {'transfer_request_id': transfer_request_id},
        {'$set': {'request_status': REQUEST_APPROVED}},
        return_document=True
    )

    if updated_document and '_id' in updated_document:
        del updated_document['_id']

    healthcare_provider_url = get_healthcare_provider_url(healthcare_provider_from_id, REQUEST_UPDATE_ENDPOINT)
    status_code, access_token = get_access_token_ghs()
    headers = {
        'Authorization': f'Bearer {access_token}'
    }

    data = {
        'transfer_request_id' : from_transfer_request_id,
        'transfer_request_status' : REQUEST_APPROVED
    }

    response = requests.post(healthcare_provider_url, json=data, headers=headers)
    if response.status_code == 200:
        print(f'Request status updated successfully: {REQUEST_APPROVED}')
        print(response.json())
    else:
        print(f'Failed to sent request: {response.status_code}')
        print(response.text)

    add_transaction_to_blockchain(updated_document)
    
    return jsonify({"message": "Request approved successfully"}), 200

@app.route('/api/data/patient/transfer/request/status/update', methods=['POST'])
@token_required_external_call
def patient_data_transfer_request_status_update():
    data = sanitize_input(request.json)

    transfer_request_id = int(data['transfer_request_id'])
    transfer_request_status = int(data['transfer_request_status'])


    updated_document = transfer_request_sent_collection.find_one_and_update(
        {'transfer_request_id': transfer_request_id},
        {'$set': {'request_status': transfer_request_status}},
        return_document=True
    )

    add_transaction_to_blockchain(updated_document)

    return jsonify({"message": "Request status updated successfully"}), 200

@app.route('/api/staff/patient/data/transfer/send/<transfer_request_id>', methods=['GET'])
@token_required_internal_call
@role_required
def patient_data_transfer_send(transfer_request_id):

    transfer_request_id = int(escape(transfer_request_id))

    if transfer_request_id is None:
        return jsonify({"error": "Invalid Request Id"}), 400
    
    transfer_request = transfer_request_received_collection.find_one({'transfer_request_id': transfer_request_id})
    transfer_request_status = int(transfer_request.get('request_status'))

    if(transfer_request_status < REQUEST_APPROVED):
        return jsonify({"error": "Patient's Approval Required to Transfer Data"}), 400

    patient_id = int(transfer_request.get('patient_id'))
    from_transfer_request_id = int(transfer_request.get('from_transfer_request_id'))

    patient = patients_collection.find_one({'patient_id': patient_id})
    patient = aes_encryption.decrypt_collection_document(patient)
    user = users_collection.find_one({'user_id' : patient['user_id']})
    user = aes_encryption.decrypt_collection_document(user)

    patient['to_transfer_request_id'] = transfer_request_id
    patient['from_transfer_request_id'] = from_transfer_request_id
    patient['request_status'] = PATIENT_DATA_TRANSFERRED
    patient['email_address'] = user['email_address']
    patient['original_healthcare_provider_id'] = patient['healthcare_provider_id'] 
    del patient['_id']
    del patient['patient_id']
    del patient['user_id']
    del patient['healthcare_provider_id']

    if not patient:
        return jsonify({"error": "Patient not found"}), 404

    for consultation in patient.get('consultation', []):
        staff_id = consultation.get('staff_id')
        if staff_id:
            staff = staffs_collection.find_one({'staff_id': staff_id}, {'first_name': 1, 'last_name': 1})
            if staff:
                staff = aes_encryption.decrypt_collection_document(staff)
                staff_name = f"{staff['first_name']} {staff['last_name']}"
            else:
                staff_name = "Unknown Staff"
            consultation['staff_name'] = staff_name
            del consultation['staff_id']

    encrypted_data, encrypted_private_pem, encrypted_public_pem = encrypt_transfer_data(patient)
    rsa_encryption.insert_encryted_document_key(transfer_request_id, encrypted_private_pem, encrypted_public_pem)

    request_from_healthcare_provider_id = transfer_request.get('request_from_healthcare_provider_id')
    healthcare_provider_url = get_healthcare_provider_url(request_from_healthcare_provider_id, TRANSFER_ENDPOINT)
    status_code, access_token = get_access_token_ghs()
    headers = {
        'Authorization': f'Bearer {access_token}'
    }

    response = requests.post(healthcare_provider_url, json=encrypted_data, headers=headers)
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

    add_transaction_to_blockchain(patient)

    return jsonify({"message": "Patient data sent successfully", "data": patient}), 200

@app.route('/api/staff/patient/data/transfer/receive', methods=['POST'])
@token_required_external_call
def patient_data_transfer_receive():
    patient_data = sanitize_input(request.json)

    to_transfer_request_id = int(patient_data['to_transfer_request_id'])
    from_transfer_request_id = int(patient_data['from_transfer_request_id'])

    transfer_request = transfer_request_sent_collection.find_one({'transfer_request_id': from_transfer_request_id})
    request_to_healthcare_provider_id = transfer_request.get('request_to_healthcare_provider_id')

    healthcare_provider_url = get_healthcare_provider_url(request_to_healthcare_provider_id, KEY_ENDPOINT)
    status_code, access_token = get_access_token_ghs()
    headers = {
        'Authorization': f'Bearer {access_token}'
    }

    key = None
    response = requests.get(f'{healthcare_provider_url}/{to_transfer_request_id}', headers=headers)
    if response.status_code == 200:
        print(f'Request key fetched successfully: ')
        data = response.json()
        encrypted_key = data['key']
        key = aes_encryption.decrypt_dek(encrypted_key, kek_common_bytes)
    else:
        print(f'Failed to sent request: {response.status_code}')
        print(response.text)

    patient_data = decrypt_tranfer_data(patient_data, key)

    add_transaction_to_blockchain(patient_data)

    last_patient = patients_collection.find_one(sort=[("patient_id", -1)])
    new_patient_id = last_patient['patient_id'] + 1 if last_patient else 1

    healthcare_provider = healthcare_provider_collection.find_one(sort=[("healthcare_provider_id", -1)])
    healthcare_provider_id = healthcare_provider['healthcare_provider_id'] if last_patient else 1

    patient_data['patient_id'] = new_patient_id
    patient_data['healthcare_provider_id'] = healthcare_provider_id
    patient_data['request_status'] = PATIENT_DATA_RECEIVED

    email_address = patient_data['email_address']
    del patient_data['email_address']

    last_user = users_collection.find_one(sort=[("user_id", -1)])
    new_user_id = last_user['user_id'] + 1 if last_user else 1

    user = {
        'user_id': new_user_id,
        'email_address': email_address,
        'password': generate_strong_password(),
        'role': PATIENT
    }
    user, encrypted_dek = aes_encryption.encrypt_collection_document(user)
    result = users_collection.insert_one(user)
    inserted_id = result.inserted_id
    aes_encryption.insert_encryted_document_key(inserted_id, encrypted_dek)

    patient_data['user_id'] = new_user_id

    patient_data, encrypted_dek = aes_encryption.encrypt_collection_document(patient_data)
    result = patients_collection.insert_one(patient_data)
    inserted_id = result.inserted_id
    aes_encryption.insert_encryted_document_key(inserted_id, encrypted_dek)

    transfer_request_sent_collection.update_one(
        { 'transfer_request_id': from_transfer_request_id },
        {
            '$set': {
                'request_status' : PATIENT_DATA_RECEIVED,
                'to_transfer_request_id' : to_transfer_request_id
            }
        }
    )

    return jsonify({"message": "Patient data received successfully"}), 200

@app.route('/api/staff/transfer/request/patient/data/integrity/check/<transfer_request_id>', methods=['GET'])
@token_required_internal_call
@role_required
def transfer_patient_data_integrity_check(transfer_request_id):
    transfer_request_id = int(escape(transfer_request_id))

    if transfer_request_id is None:
        return jsonify({"error": "Invalid Request Id"}), 400

    transfer_request = transfer_request_sent_collection.find_one({'transfer_request_id': transfer_request_id})
    request_to_healthcare_provider_id = transfer_request["request_to_healthcare_provider_id"]
    to_transfer_request_id = transfer_request["to_transfer_request_id"]

    result = blockchain_collection.find_one({"transactions.to_transfer_request_id": to_transfer_request_id, "transactions.request_status": PATIENT_DATA_TRANSFERRED})
    received_data = result['transactions'][0]
    received_data_hash = hashlib.sha256(json.dumps(received_data, sort_keys=True).encode()).hexdigest()

    healthcare_provider_url = get_healthcare_provider_url(request_to_healthcare_provider_id, INTEGRITY_ENDPOINT)
    status_code, access_token = get_access_token_ghs()
    headers = {
        'Authorization': f'Bearer {access_token}'
    }

    data = {
        'transfer_request_id' : transfer_request_id,
        'data_hash' : received_data_hash
    }

    response = requests.post(healthcare_provider_url, json=data, headers=headers)
    message = None
    if response.status_code == 200:
        response_data = response.json()
        message = response_data['message']
    else:
        print(f'Failed to sent request: {response.status_code}')
        print(response.text)

    return jsonify({'message': message}), 200

@app.route('/api/staff/patient/data/integrity/check', methods=['POST'])
@token_required_external_call
def patient_data_integrity_check():
    data = sanitize_input(request.json)
    transfer_request_id = int(data['transfer_request_id'])
    received_data_hash = data['data_hash']

    result = blockchain_collection.find_one({"transactions.to_transfer_request_id": transfer_request_id, "transactions.request_status": PATIENT_DATA_TRANSFERRED})
    sent_data = result['transactions'][0]
    sent_data_hash = hashlib.sha256(json.dumps(sent_data, sort_keys=True).encode()).hexdigest()

    if received_data_hash == sent_data_hash:
        return jsonify({'status': 'Success', 'message': 'Data integrity verified'}), 200
    else:
        return jsonify({'status': 'Failure', 'message': 'Data is compromised'}), 400

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, port=os.getenv('PORT'))
