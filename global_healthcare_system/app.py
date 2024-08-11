from flask import Flask, jsonify, request
from pymongo import MongoClient
from dotenv import load_dotenv
import os
from urllib.parse import urlparse
import aes_encryption
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["5 per minute", "50 per hour"]
)
limiter.init_app(app)

load_dotenv()

client = MongoClient(os.getenv('MONGO_URI'))
db = client[os.getenv('GLOBAL_DB_NAME')]
healthcare_provider_collection = db['healthcare_provider']

@app.route('/api/get/all/healthcareprovider/details', methods=['GET'])
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
        return str(e), 500

@app.route('/api/get/healthcareprovider/<healthcare_provider_id>', methods=['GET'])
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
        return str(e), 500

if __name__ == '__main__':
    app.run(debug=True, port=5002)
