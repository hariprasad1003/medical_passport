from flask import Flask, jsonify, request
from pymongo import MongoClient
from dotenv import load_dotenv
import os
from urllib.parse import urlparse

app = Flask(__name__)

load_dotenv()

client = MongoClient(os.getenv('MONGO_URI'))
db = client[os.getenv('GLOBAL_DB_NAME')]
healthcare_provider_collection = db['healthcare_provider']

@app.route('/api/get/all/healthcareprovider/details', methods=['GET'])
def get_all_healthcare_provider_details():
    try:
        all_healthcare_providers = healthcare_provider_collection.find({}, {'_id': 0})
        providers_list = list(all_healthcare_providers)
        
        return jsonify(providers_list), 200
    except Exception as e:
        return str(e), 500

@app.route('/api/get/healthcareprovider/<healthcare_provider_id>', methods=['GET'])
def get_healthcare_provider_by_id(healthcare_provider_id):
    try:
        healthcare_provider = healthcare_provider_collection.find_one({'healthcare_provider_id': int(healthcare_provider_id)}, {'_id': 0})

        if healthcare_provider:
            return jsonify(healthcare_provider), 200
        else:
            return jsonify({'error': 'Healthcare provider not found'}), 404
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    app.run(debug=True, port=5002)
