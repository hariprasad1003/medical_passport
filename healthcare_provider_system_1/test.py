import os
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

client = MongoClient(os.getenv('MONGO_URI'))
db = client[os.getenv('DB_NAME')]
patient_collection = db['patient']

def find_patient_by_first_name(first_name, last_name, date_of_birth, house_number, post_code, country):
    formatted_first_name = first_name.title()
    formatted_last_name = last_name.title()
    
    patients_with_same_first_name = patient_collection.find({'first_name': formatted_first_name})
    
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

received_data = {
    'first_name': 'Dennis',
    'last_name': 'Byrne',
    'date_of_birth': '1999-07-18',
    'house_number': '7',
    'post_code': 'LN1N6AH',
    'country': 'UK'
}

patient = find_patient_by_first_name(
    received_data['first_name'],
    received_data['last_name'],
    received_data['date_of_birth'],
    received_data['house_number'],
    received_data['post_code'],
    received_data['country']
)

if patient:
    user_id = patient.get('user_id')
    print(f"Found patient with user ID: {user_id}")
else:
    print("No matching patient found.")
