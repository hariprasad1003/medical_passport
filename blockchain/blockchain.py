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
        return [self.convert_block_id_to_str(block) for block in chain_data]

    def convert_block_id_to_str(self, block):
        block['_id'] = str(block['_id'])
        return block

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

        self.current_transactions = []

        self.save_block(block)

        block['_id'] = str(block['_id'])

        self.chain.append(block)
        return block

    def new_transaction(self, sender, recipient, data):
        self.current_transactions.append({
            'sender': sender,
            'recipient': recipient,
            'data': data,
        })

        return self.last_block['index'] + 1

    @staticmethod
    def hash(block):
        # Convert _id to str if it's an ObjectId
        block_copy = dict(block)
        if isinstance(block_copy.get('_id'), ObjectId):
            block_copy['_id'] = str(block_copy['_id'])

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
