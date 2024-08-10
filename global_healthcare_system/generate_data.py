import os
import random
import string
import json
import pandas as pd
from datetime import datetime, timedelta, date, time
from faker import Faker
from pymongo import MongoClient
from dotenv import load_dotenv


fake = Faker()
fake_uk = Faker('en_GB')
fake_us = Faker('en_US')

load_dotenv()

healthcare_provider_id = 1

user_roles = [0, 1]
staff_roles = [0, 1]

consultation_hours_options = [
    "Mon-Fri 9AM-5PM",
    "Mon-Thu 8AM-4PM",
    "Tue-Sat 10AM-6PM",
    "Mon-Wed 8AM-2PM",
    "Wed-Sun 11AM-6PM",
]

specializations = ["Cardiology", "Endocrinology", "Orthopedics", "Neurology", "Oncology", "Nephrology", "Pulmonology", "Gastroenterology", "Allergy and Immunology", "General Practice (Family Medicine)"]

qualifications = {
    0: [
        "MBA Healthcare",
        "BBA",
        "MHA (Master of Health Administration)",
        "BA in Business Administration",
        "Certification in Healthcare Management"
    ],
    1: [
        "MBBS",
        "MD",
        "DO",
        "PhD in Medical Science",
        "DM",
        "FRCS"
    ]
}

increment_number = 0

'''
FUNCTIONS
'''

def generate_increment_number():
    global increment_number
    increment_number += 1
    return increment_number

def generate_first_name_and_last_name(country):
    first_name = None
    last_name = None

    if country == 'USA':
        first_name = fake_us.first_name()
        last_name = fake_us.last_name()
    elif country == 'UK':
        first_name = fake_uk.first_name()
        last_name = fake_uk.last_name()

    return first_name, last_name  

def generate_email_and_phone_number(country):
    email_address = None
    phone_number = None

    if country == 'USA':
        email_address = fake_us.email()
        phone_number = fake_us.phone_number()
    elif country == 'UK':
        email_address = fake_uk.email()
        phone_number = fake_uk.phone_number()

    return email_address, phone_number    

def generate_address(country):
    house_number = None
    post_code = None
    
    if country == 'USA':
        house_number = fake_us.building_number()
        post_code = fake_us.zipcode()
    elif country == 'UK':
        house_number = fake_uk.building_number()
        post_code = fake_uk.postcode()
    
    address = {
        "house_number": house_number,
        "post_code": post_code,
        "country": country
    }

    return address

def generate_strong_password(length=12):
    characters = string.ascii_letters + string.digits + string.punctuation
    password = ''.join(random.choices(characters, k=length))
    return password

def generate_consultation_hours(role):
    if role in ["Doctor", "Nurse"]:
        return random.choice(consultation_hours_options)
    return None

def generate_specialization(role):
    if role == "Doctor":
        return random.choice(specializations)
    return None

def random_date_of_birth(age):
    current_date = datetime.now()
    start_date = current_date - timedelta(days=age * 365 + 365)
    end_date = current_date - timedelta(days=age * 365)
    random_days = random.randint(0, (end_date - start_date).days)
    birth_date = start_date + timedelta(days=random_days)
    return birth_date

def random_time():
    random_seconds = random.randint(0, 86399)
    return (datetime.min + timedelta(seconds=random_seconds)).time()

def serialize_dates(data):
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (datetime, date)):
                data[key] = value.isoformat()
            elif isinstance(value, time):
                data[key] = value.strftime("%H:%M:%S")
            elif isinstance(value, list):
                data[key] = [serialize_dates(item) for item in value]
            elif isinstance(value, dict):
                data[key] = serialize_dates(value)
    elif isinstance(data, list):
        data = [serialize_dates(item) for item in data]
    return data

'''
COLLECTIONS
'''

def generate_global_healthcare_provider(country):
    increment_number = generate_increment_number()
    healthcare_provider_name = f"Healthcare Provider {increment_number}"

    return {
        "healthcare_provider_id": increment_number,
        "healthcare_provider_name": healthcare_provider_name,
        'domain' : None,
        "address": generate_address(country)
    }
        
def generate_healthcare_provider(country):
    increment_number = generate_increment_number()
    healthcare_provider_name = f"Healthcare Provider {increment_number}"

    return {
        "healthcare_provider_id": increment_number,
        "healthcare_provider_name": healthcare_provider_name,
        "address": generate_address(country)
    }

def generate_user(country):
    email_address, phone_number = generate_email_and_phone_number(country)
    return {
        "user_id": generate_increment_number(),
        "email_address": email_address,
        "phone_number": phone_number,
        "password": generate_strong_password(),
        "role": random.choice(user_roles)
    }

def generate_staff(country):
    staff_role = random.choice(staff_roles)
    first_name, last_name = generate_first_name_and_last_name(country)
    return {
        "staff_id": generate_increment_number(),
        "user_id": None,
        "healthcare_provider_id": healthcare_provider_id,
        "first_name": first_name,
        "last_name": last_name,
        "role": staff_role,
        "address": generate_address(country),
        "specialization": generate_specialization(staff_role),
        "years_of_experience": random.randint(1, 40),
        "qualifications": random.choice(qualifications[staff_role]),
        "consultation_hours": generate_consultation_hours(staff_role)
    }

def generate_patient(country, iterations):
    file_path = 'Hospital Patient Records Dataset.xlsx'
    df = pd.read_excel(file_path)

    total_rows = len(df)
    random_index = random.randint(0, total_rows - 1)
    random_row = df.iloc[random_index]

    age = random_row['Age']
    gender = random_row['Gender']

    first_name, last_name = generate_first_name_and_last_name(country)
    
    consultation_list = []
    diagnosis_list = []
    medication_list = []

    for i in range(random.randint(0, 5)):

        random_index_1 = random.randint(0, total_rows - 1)
        random_row_1 = df.iloc[random_index_1]

        identifier = generate_increment_number()

        diagnosis = random_row_1['Diagnosis']
        procedure = random_row_1['Procedure']

        consultation = {
            "consultation_id": identifier,
            "staff_id": None,
            "date": fake.date_this_decade(),
            "time": random_time(),
            "follow_up_date": fake.date_this_decade(),
            "notes": fake.text(max_nb_chars=200)
        }

        consultation_list.append(consultation)

        diagnosis = {
            "diagnosis_id": identifier,
            "consultation_id": identifier,
            "diagnosis": diagnosis,
            "procedure": procedure,
            "date": fake.date_this_decade(),
            "time": random_time(),
            "notes": fake.text(max_nb_chars=200)
        }

        diagnosis_list.append(diagnosis)

        medication = {
            "medication_id": identifier,
            "consultation_id": identifier,
            "name": fake.word(),
            "dosage": f"{random.randint(1, 500)} mg",
            "start_date": fake.date_this_decade(),
            "end_date": fake.date_this_decade(),
            "instructions": fake.sentence()
        }

        medication_list.append(medication)

    return {
        "patient_id": 1,
        "user_id": None,
        "healthcare_provider_id": healthcare_provider_id,
        "first_name": first_name,
        "last_name": last_name,
        "date_of_birth": random_date_of_birth(int(age)),
        "age": int(age),
        "gender": gender,
        "address": generate_address(country),
        "consultation": consultation_list,
        "diagnosis": diagnosis_list,
        "medication": medication_list
    }

'''
GENERATE
'''

'''
UK, USA
'''

iterations = 1
country = 'UK'

def insert_json_to_mongodb(collection_name, json_data):
    client = MongoClient(os.getenv('MONGO_URI'))
    '''
    GLOBAL_DB_NAME, DB_NAME, DB_NAME_2
    '''
    db = client[os.getenv('DB_NAME')]
    collection = db[collection_name]
    
    if isinstance(json_data, list):
        result = collection.insert_many(json_data)
    else:
        result = collection.insert_one(json_data)
    
    if isinstance(json_data, list):
        print(f"Inserted IDs: {result.inserted_ids}")
    else:
        print(f"Inserted ID: {result.inserted_id}")

def update_patient():
    client = MongoClient(os.getenv('MONGO_URI'))
    db = client[os.getenv('DB_NAME')]
    patient_collection = db['patient']
    
    updated_document = {}
    for document in patient_collection.find():
        file_path = 'Hospital Patient Records Dataset.xlsx'
        df = pd.read_excel(file_path)

        total_rows = len(df)
        random_index = random.randint(0, total_rows - 1)
        random_row = df.iloc[random_index]

        age = random_row['Age']
        gender = random_row['Gender']

        date_of_birth = random_date_of_birth(int(age))
        
        first_name, last_name = generate_first_name_and_last_name(country)  

        address = generate_address(country)
        
        for key, value in document.items():
            if key == 'first_name':
                updated_document[key] = first_name
            elif key == 'last_name':
                updated_document[key] = last_name
            elif key == 'date_of_birth':
                updated_document[key] = str(date_of_birth)
            elif key == 'gender':
                updated_document[key] = gender
            elif key == 'age':
                updated_document[key] = str(age)
            elif key == 'address':
                updated_document[key] = address
        patient_collection.update_one({'_id': document['_id']}, {'$set': updated_document})

# healthcare_providers = [generate_healthcare_provider(country) for _ in range(iterations)]
# print(json.dumps(healthcare_providers, indent=4))

# users = [generate_user(country) for _ in range(iterations)]
# print(json.dumps(users, indent=4))

# staffs = [generate_staff(country) for _ in range(iterations)]
# print(json.dumps(staffs, indent=4))

# patient = generate_patient(country, iterations)
# patient_serialized = serialize_dates(patient)
# print(patient_serialized)

# healthcare_providers = [generate_global_healthcare_provider(country) for _ in range(iterations)]
# print(json.dumps(healthcare_providers, indent=4))

'''
collection_names:

healthcare_provider
user
staff
patient
'''

collection_name = 'healthcare_provider'
# insert_json_to_mongodb(collection_name, healthcare_provider)
update_patient()

