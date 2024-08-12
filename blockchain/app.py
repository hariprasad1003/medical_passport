from flask import Flask, request, jsonify
from pymongo import MongoClient
from blockchain import Blockchain
from dotenv import load_dotenv
import os

app = Flask(__name__)

load_dotenv()

client = MongoClient(os.getenv('MONGO_URI'))
db = client[os.getenv('DB_NAME')]
blockchain_collection = db['blockchain']

blockchain = Blockchain(blockchain_collection)

@app.route('/api/blockchain/add/transaction', methods=['POST'])
def transfer_phr():
    values = request.get_json()

    required = ['sender', 'recipient', 'data']
    if not all(k in values for k in required):
        return 'Missing values', 400

    index = blockchain.new_transaction(values['sender'], values['recipient'], values['data'])

    last_proof = blockchain.last_block['proof']
    proof = blockchain.proof_of_work(last_proof)

    previous_hash = blockchain.hash(blockchain.last_block)
    block = blockchain.new_block(proof, previous_hash)

    return jsonify({
        'message': f'PHR transferred and recorded in Block {block["index"]}',
        'block': block
    }), 201

@app.route('/api/get/chain', methods=['GET'])
def full_chain():
    chain = list(blockchain.db_collection.find().sort("index", 1))
    return jsonify({
        'chain': chain,
        'length': len(chain),
    }), 200

@app.route('/api/validate_chain', methods=['GET'])
def validate_chain():
    is_valid = blockchain.is_chain_valid()
    if is_valid:
        response = {'message': 'The blockchain is valid.'}
    else:
        response = {'message': 'The blockchain is invalid!'}
    return jsonify(response), 200

if __name__ == '__main__':
    app.run(debug=True, port=5003)