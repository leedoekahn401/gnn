from mesa import Model
from mesa.datacollection import DataCollector
from .agents import NormalAgent, FraudAgent
import uuid
import datetime
import random

class TransactionModel(Model):
    """A model with some number of users conducting transactions."""
    
    def __init__(self, num_normal=50, num_fraud=10, seed=None):
        super().__init__()
        self.num_normal = num_normal
        self.num_fraud = num_fraud
        self.transactions = [] # Store transaction edges
        self.users = [] # Store our agents manually to avoid Mesa version issues
        self.current_step = 0
        
        # Create normal agents
        for i in range(self.num_normal):
            agent_id = f"user_normal_{i}"
            a = NormalAgent(agent_id, self)
            self.users.append(a)
            
        # Create fraud agents
        for i in range(self.num_fraud):
            agent_id = f"user_fraud_{i}"
            a = FraudAgent(agent_id, self)
            self.users.append(a)

    def record_transaction(self, source, target, amount, is_fraud):
        tx_id = str(uuid.uuid4())
        timestamp = datetime.datetime.now().isoformat()
        
        self.transactions.append({
            "tx_id": tx_id,
            "source": source,
            "target": target,
            "amount": amount,
            "timestamp": timestamp,
            "is_fraud": is_fraud,
            "step": self.current_step
        })

    def step(self):
        """Advance the model by one step."""
        self.current_step += 1
        random.shuffle(self.users)
        for agent in self.users:
            agent.step()

    def get_transactions(self):
        return self.transactions
        
    def get_users(self):
        user_data = []
        for agent in self.users:
            user_data.append({
                "id": agent.unique_id,
                "is_fraud": agent.is_fraud,
                "balance": agent.balance
            })
        return user_data
