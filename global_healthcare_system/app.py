from flask import Flask, jsonify, request
from pymongo import MongoClient
from dotenv import load_dotenv
import os
from urllib.parse import urlparse
import aes_encryption
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import jwt
from functools import wraps
from datetime import datetime, timedelta

app = Flask(__name__)

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["5 per minute", "50 per hour"]
)
limiter.init_app(app)

load_dotenv()

app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')

client = MongoClient(os.getenv('MONGO_URI'))
db = client[os.getenv('GLOBAL_DB_NAME')]
healthcare_provider_collection = db['healthcare_provider']

def create_token(healthcare_provider_id):
    token = jwt.encode({
        'healthcare_provider_id': healthcare_provider_id,
        'exp': datetime.utcnow() + timedelta(minutes=30)
    }, app.config['JWT_SECRET_KEY'], algorithm='HS256')
    return token

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):

        token_from_request = request.headers.get('Authorization')

        if not token_from_request and not token_from_session:
            return jsonify({'message': 'Token is missing!'}), 403

        try:
            token_from_request = token_from_request.split(" ")[1]
            data = jwt.decode(token_from_request, app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired!'}), 403
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Invalid token!'}), 403

        return f(*args, **kwargs)

    return decorated

@app.route('/api/authenticate/get/accesstoken/healthcareprovider/<healthcare_provider_id>', methods=['GET'])
def get_access_token_for_healthcare_provider(healthcare_provider_id):
    try:
        client_id = str(request.headers.get('Client-Id'))
        client_token = str(request.headers.get('Client-Token'))

        if not client_id or not client_token:
            return jsonify({'error': 'Client-Id and Client-Token headers are required.'}), 400

        healthcare_provider = healthcare_provider_collection.find_one({'healthcare_provider_id': int(healthcare_provider_id)})
        healthcare_provider = aes_encryption.decrypt_collection_document(healthcare_provider)
        healthcare_provider_client_id = str(healthcare_provider['client_id'])
        healthcare_provider_client_token = str(healthcare_provider['client_token'])
        
        if(client_id == healthcare_provider_client_id and client_token == healthcare_provider_client_token):
            access_token = create_token(healthcare_provider_id)
            return jsonify({'access_token': access_token}), 200
        else:
            return jsonify({'error': 'Invalid Client-Id or Client-Token.'}), 400
    except Exception as e:
        return jsonify({'message': str(e)}), 500

@app.route('/api/healthcareprovider/validate/accesstoken', methods=['POST'])
@token_required
def validate_healthcare_provider_access_token():
    try:
        data = request.json
        access_token = data['access_token']
        try:
            data = jwt.decode(access_token, app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
            return jsonify({'message': 'Token validation has successful!'}), 200
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired!'}), 403
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Invalid token!'}), 403
    except Exception as e:
        return jsonify({'message': str(e)}), 500

@app.route('/api/get/all/healthcareprovider/details', methods=['GET'])
@token_required
def get_all_healthcare_provider_details():
    try:
        all_healthcare_providers_list = list(healthcare_provider_collection.find())
        healthcare_providers_list = []
        for healthcare_provider in all_healthcare_providers_list:
            healthcare_provider = aes_encryption.decrypt_collection_document(healthcare_provider)
            del healthcare_provider['_id']
            healthcare_providers_list.append(healthcare_provider)
        
        return jsonify(healthcare_providers_list), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500

@app.route('/api/get/healthcareprovider/<healthcare_provider_id>', methods=['GET'])
@token_required
def get_healthcare_provider_by_id(healthcare_provider_id):
    try:
        healthcare_provider = healthcare_provider_collection.find_one({'healthcare_provider_id': int(healthcare_provider_id)})
        healthcare_provider = aes_encryption.decrypt_collection_document(healthcare_provider)
        del healthcare_provider['_id']
        
        if healthcare_provider:
            return jsonify(healthcare_provider), 200
        else:
            return jsonify({'error': 'Healthcare provider not found'}), 404
    except Exception as e:
        return jsonify({'message': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5002)
