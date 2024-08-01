import os
from pymongo import MongoClient
from dotenv import load_dotenv
from bson.json_util import dumps
from flask import Flask, render_template, request, redirect, url_for, session

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
        json_data = dumps(providers_list)    
        return json_data, 200
    except Exception as e:
        return str(e), 500  

if __name__ == '__main__':
    app.run(debug=True, port=5002)