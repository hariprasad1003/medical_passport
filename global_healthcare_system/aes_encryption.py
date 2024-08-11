import os
import base64
import hashlib
from pymongo import MongoClient
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from dotenv import load_dotenv
import uuid
import secrets

load_dotenv()

MASTER_KEY = os.getenv('MASTER_KEY')
KEK = os.getenv('KEK')

kek_bytes = base64.b64decode(KEK)

if len(kek_bytes) not in [16, 24, 32]:
    raise ValueError(f"Incorrect KEK length: {len(kek_bytes)} bytes. It must be 16, 24, or 32 bytes.")

mongo_client = MongoClient(os.getenv('MONGO_URI'))
db = mongo_client[os.getenv('GLOBAL_DB_NAME')]

healthcare_provider_collection = db['healthcare_provider']
user_collection = db['user']
patient_collection = db['patient']
staff_collection = db['staff']
transfer_request_sent_collection = db['transfer_request_sent']
key_collection = db['key']

non_encrypt_list = ['_id', 'user_id', 'email_address', 'role', 'healthcare_provider_id', 'patient_id', 'staff_id', 'transfer_request_id', 'request_from_healthcare_provider_id', 'request_to_healthcare_provider_id', 'request_type', 'request_status']

collections = [
    healthcare_provider_collection
]

def generate_master_key():
    master_key = os.urandom(32)
    return base64.b64encode(master_key).decode()

def generate_dek(master_key):
    master_key_bytes = base64.b64decode(master_key)
    salt = get_random_bytes(16)
    dek = hashlib.sha256(master_key_bytes + salt).digest()
    return dek

def generate_kek():
    kek = os.urandom(32)
    return base64.b64encode(kek).decode()

def generate_jwt_secret_key():
    return secrets.token_hex(32)

def generate_client_id():
    return str(uuid.uuid4())

def generate_client_token():
    return secrets.token_hex(32) 

def pad(data):
    pad_length = 16 - len(data) % 16
    return data + bytes([pad_length] * pad_length)

def unpad(data):
    pad_length = data[-1]
    return data[:-pad_length]

def encrypt_dek(dek, kek):
    iv = get_random_bytes(16)
    cipher = AES.new(kek, AES.MODE_CBC, iv)
    padded_dek = pad(dek)
    encrypted_dek = cipher.encrypt(padded_dek)
    return base64.b64encode(iv + encrypted_dek).decode()

def decrypt_dek(encrypted_dek, kek):
    encrypted_dek = base64.b64decode(encrypted_dek)
    iv = encrypted_dek[:16]
    encrypted_dek = encrypted_dek[16:]
    cipher = AES.new(kek, AES.MODE_CBC, iv)
    decrypted_padded_dek = cipher.decrypt(encrypted_dek)
    return unpad(decrypted_padded_dek)

def encrypt_data(data, data_key):
    iv = get_random_bytes(16)
    cipher = AES.new(data_key, AES.MODE_CBC, iv)
    padded_data = pad(data.encode())
    encrypted_data = cipher.encrypt(padded_data)
    return base64.b64encode(iv + encrypted_data).decode()

def decrypt_data(encrypted_data, data_key):
    encrypted_data = base64.b64decode(encrypted_data)
    iv = encrypted_data[:16]
    encrypted_data = encrypted_data[16:]
    cipher = AES.new(data_key, AES.MODE_CBC, iv)
    decrypted_padded_data = cipher.decrypt(encrypted_data)
    return unpad(decrypted_padded_data).decode()

def encrypt_document(document, non_encrypt_list, dek):
    encrypted_document = {}

    for key, value in document.items():
        if key not in non_encrypt_list:
            if isinstance(value, str):
                encrypted_document[key] = encrypt_data(value, dek)
            elif isinstance(value, dict):
                encrypted_document[key] = encrypt_document(value, non_encrypt_list, dek)
            elif isinstance(value, list):
                encrypted_document[key] = [
                    encrypt_document(item, non_encrypt_list, dek) if isinstance(item, dict) else encrypt_data(item, dek) if isinstance(item, str) else item 
                    for item in value
                ]
            else:
                encrypted_document[key] = value
        else:
            encrypted_document[key] = value

    return encrypted_document

def encrypt_collection_data(collection, non_encrypt_list, master_key, kek):
    for document in collection.find():
        dek = generate_dek(master_key)
        encrypted_dek = encrypt_dek(dek, kek)
        updated_document = encrypt_document(document, non_encrypt_list, dek)
        collection.update_one({'_id': document['_id']}, {'$set': updated_document})
        key_collection.insert_one({'document_id': document['_id'], 'encrypted_dek': encrypted_dek})

def decrypt_document(document, non_encrypt_list, dek):
    decrypted_document = {}

    for key, value in document.items():
        if key not in non_encrypt_list:
            if isinstance(value, str):
                decrypted_document[key] = decrypt_data(value, dek)
            elif isinstance(value, dict):
                decrypted_document[key] = decrypt_document(value, non_encrypt_list, dek)
            elif isinstance(value, list):
                decrypted_document[key] = [
                    decrypt_document(item, non_encrypt_list, dek) if isinstance(item, dict) else decrypt_data(item, dek) if isinstance(item, str) else item
                    for item in value
                ]
            else:
                decrypted_document[key] = value
        else:
            decrypted_document[key] = value

    return decrypted_document

def decrypt_collection_data(collection, non_encrypt_list, kek):
    for document in collection.find():
        key_info = key_collection.find_one({'document_id': document['_id']})
        encrypted_dek = key_info['encrypted_dek']
        dek = decrypt_dek(encrypted_dek, kek)
        decrypted_document = decrypt_document(document, non_encrypt_list, dek)
        print(decrypted_document)
        
        # collection.update_one({'_id': document['_id']}, {'$set': decrypted_document})
        # key_collection.delete_one({'document_id': document['_id']})

def decrypt_collection_document(document):
    key_info = key_collection.find_one({'document_id': document['_id']})
    encrypted_dek = key_info['encrypted_dek']
    dek = decrypt_dek(encrypted_dek, kek_bytes)
    decrypted_document = decrypt_document(document, non_encrypt_list, dek)
    return decrypted_document

def delete_keys(collection):
    for document in collection.find():
        key_collection.delete_one({'document_id': document['_id']})

if __name__ == '__main__':
    pass
    # print(generate_master_key())
    # print(generate_kek())
    # print(generate_jwt_secret_key())
    # print(generate_client_id())
    # print(generate_client_token())

    # for collection in collections:
        # encrypt_collection_data(collection, non_encrypt_list, MASTER_KEY, kek_bytes)
        # decrypt_collection_data(collection, non_encrypt_list, kek_bytes)
        # delete_keys(collection)
