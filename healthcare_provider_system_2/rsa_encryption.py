import os
import base64
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
import aes_encryption
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

KEK2 = os.getenv('KEK2')
kek2_bytes = base64.b64decode(KEK2)

mongo_client = MongoClient(os.getenv('MONGO_URI'))
db = mongo_client[os.getenv('DB_NAME')]

key_collection = db['key']

non_encrypt_list = ['_id', 'user_id', 'email_address', 'role', 'healthcare_provider_id', 'patient_id', 'staff_id', 'transfer_request_id', 'request_from_healthcare_provider_id', 'request_to_healthcare_provider_id', 'request_type', 'request_status']

def generate_keys():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
    public_key = private_key.public_key()
    return private_key, public_key

def encrypt_data(data, public_key):
    if isinstance(data, str):
        data_bytes = data.encode('utf-8')
    else:
        data_bytes = str(data).encode('utf-8')
    
    encrypted_data = public_key.encrypt(data_bytes, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    return encrypted_data

def encrypt_document(document, public_key):
    encrypted_document = {}

    for key, value in document.items():
        if key not in non_encrypt_list:
            if isinstance(value, str):
                encrypted_document[key] = encrypt_data(value, public_key)
            elif isinstance(value, dict):
                encrypted_document[key] = encrypt_document(value, public_key)
            elif isinstance(value, list):
                encrypted_document[key] = [encrypt_document(item, public_key) if isinstance(item, dict) else encrypt_data(item, public_key) for item in value]
            else:
                encrypted_document[key] = value
        else:
            encrypted_document[key] = value

    return encrypted_document

def encode_to_base64(data):
    if isinstance(data, bytes):
        return base64.b64encode(data).decode('utf-8')
    elif isinstance(data, dict):
        return {key: encode_to_base64(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [encode_to_base64(item) for item in data]
    else:
        return data

def decrypt_data(encrypted_data, private_key):
    if isinstance(encrypted_data, str):
        encrypted_data = base64.b64decode(encrypted_data)

    decrypted_data = private_key.decrypt(encrypted_data, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    return decrypted_data

def decrypt_document(encrypted_document, private_key):
    decrypted_document = {}
    for key, value in encrypted_document.items():
        if key not in non_encrypt_list:
            if isinstance(value, (str, bytes)):
                decrypted_value = decrypt_data(value, private_key)
                decrypted_document[key] = decrypted_value.decode('utf-8')
            elif isinstance(value, dict):
                decrypted_document[key] = decrypt_document(value, private_key)
            elif isinstance(value, list):
                decrypted_document[key] = [
                    decrypt_document(item, private_key) if isinstance(item, dict) else decrypt_data(item, private_key).decode('utf-8')
                    for item in value
                ]
            else:
                decrypted_document[key] = value
        else:
            decrypted_document[key] = value
    return decrypted_document

def decode_from_base64(data):
    if isinstance(data, str):
        try:
            return base64.b64decode(data.encode('utf-8'))
        except Exception:
            return data
    elif isinstance(data, dict):
        return {key: decode_from_base64(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [decode_from_base64(item) for item in data]
    else:
        return data

def convert_private_key_to_pem(private_key):
    pem = private_key.private_bytes(encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.PKCS8, encryption_algorithm=serialization.NoEncryption())
    return pem

def convert_public_key_to_pem(public_key):
    pem = public_key.public_bytes(encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo)
    return pem

def convert_pem_to_private_key(pem):
    private_key = serialization.load_pem_private_key(pem, password=None, backend=default_backend())
    return private_key

def convert_pem_to_public_key(pem):
    public_key = serialization.load_pem_public_key(pem, backend=default_backend())
    return public_key

def insert_encryted_document_key(request_id, encrypted_private_key, encrypted_public_key):
    key_collection.insert_one({'request_id': request_id, 'encrypted_private_key': encrypted_private_key, 'encrypted_public_key':encrypted_public_key})

def get_encrypted_document_key(request_id):
    return key_collection.find_one({'request_id': int(request_id)})

if __name__ == "__main__":
    pass

    '''
    private_key, public_key = generate_keys()
    print(private_key, public_key)

    print('-----------------------------------------------------------------------')

    private_key_pem = convert_private_key_to_pem(private_key)
    public_key_pem = convert_public_key_to_pem(public_key)
    print(private_key_pem, public_key_pem)

    print('-----------------------------------------------------------------------')

    encrypted_private_pem = aes_encryption.encrypt_dek(private_key_pem, kek2_bytes)
    encrypted_public_pem = aes_encryption.encrypt_dek(public_key_pem, kek2_bytes)
    print(encrypted_private_pem, encrypted_public_pem)

    print('-----------------------------------------------------------------------')

    decrypted_private_pem = aes_encryption.decrypt_dek(encrypted_private_pem, kek2_bytes)
    decrypted_public_pem = aes_encryption.decrypt_dek(encrypted_public_pem, kek2_bytes)
    print(decrypted_private_pem, decrypted_public_pem)

    print('-----------------------------------------------------------------------')

    decrypted_private_key = convert_pem_to_private_key(decrypted_private_pem)
    decrypted_public_key = convert_pem_to_public_key(decrypted_public_pem)
    print(decrypted_private_key, decrypted_public_key)

    print('-----------------------------------------------------------------------')

    document = {
        "name": "John Doe",
        "age": 30,
        "address": {
            "city": "New York",
            "zipcode": 10001
        },
        "interests": ["reading", "traveling", 1234],
        "is_verified": True
    }

    encrypted_doc = encrypt_document(document, public_key)
    print("Encrypted Document:", encrypted_doc)

    decrypted_doc = decrypt_document(encrypted_doc, decrypted_private_key)
    print("Decrypted Document:", decrypted_doc)

    print('-----------------------------------------------------------------------')
    '''