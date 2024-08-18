from bson.objectid import ObjectId
import hashlib
import json
from time import time

class Blockchain:
    def __init__(self, db_collection):
        self.db_collection = db_collection
        self.current_transactions = []
        self.chain = self.load_chain()

        if not self.chain:
            self.new_block(previous_hash='1', proof=100)

    def load_chain(self):
        chain_data = list(self.db_collection.find().sort("index", 1))
        return [self.convert_objectid_to_str(block) for block in chain_data]

    @staticmethod
    def convert_objectid_to_str(data):
        if isinstance(data, dict):
            return {k: Blockchain.convert_objectid_to_str(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [Blockchain.convert_objectid_to_str(item) for item in data]
        elif isinstance(data, ObjectId):
            return str(data)
        else:
            return data

    def save_block(self, block):
        self.db_collection.insert_one(block)

    def new_block(self, proof, previous_hash=None):
        block = {
            'index': len(self.chain) + 1,
            'timestamp': time(),
            'transactions': self.current_transactions,
            'proof': proof,
            'previous_hash': previous_hash or self.hash(self.chain[-1]),
        }
        print(block)

        self.current_transactions = []

        self.save_block(block)

        block['_id'] = str(block['_id'])

        self.chain.append(block)
        return block

    def new_transaction(self, data):
        data = self.convert_objectid_to_str(data)
        self.current_transactions.append(data)

        return self.last_block['index'] + 1

    @staticmethod
    def hash(block):
        block_copy = dict(block)
        
        for key, value in block_copy.items():
            if isinstance(value, ObjectId):
                block_copy[key] = str(value)
            elif isinstance(value, list):
                block_copy[key] = [str(v) if isinstance(v, ObjectId) else v for v in value]
            elif isinstance(value, dict):
                block_copy[key] = {k: str(v) if isinstance(v, ObjectId) else v for k, v in value.items()}
        
        block_string = json.dumps(block_copy, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    @property
    def last_block(self):
        return self.chain[-1]

    def proof_of_work(self, last_proof):
        proof = 0
        while self.valid_proof(last_proof, proof) is False:
            proof += 1
        return proof

    @staticmethod
    def valid_proof(last_proof, proof):
        guess = f'{last_proof}{proof}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"
