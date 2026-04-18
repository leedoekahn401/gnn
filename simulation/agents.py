import random
from mesa import Agent

class BaseUser(Agent):
    """
    Base user agent in the transaction network.
    """
    def __init__(self, unique_id, model, is_fraud=False):
        super().__init__(unique_id, model)
        self.is_fraud = is_fraud
        self.balance = random.uniform(100, 10000)

    def step(self):
        pass

class NormalAgent(BaseUser):
    """
    Normal agent that performs random transactions to other random agents.
    """
    def __init__(self, unique_id, model):
        super().__init__(unique_id, model, is_fraud=False)

    def step(self):
        # Decide if this agent wants to transact this step (e.g., 10% chance)
        if random.random() < 0.1:
            # Pick a random target
            target = self.random.choice(self.model.users)
            if target.unique_id != self.unique_id:
                # Transact a small amount
                amount = random.uniform(1, min(self.balance, 500))
                self.balance -= amount
                target.balance += amount
                
                # Record transaction in model
                self.model.record_transaction(self.unique_id, target.unique_id, amount, is_fraud=False)

class FraudAgent(BaseUser):
    """
    Fraud agent that participates in circular transactions or rug pull.
    For MVP, we'll implement a simple circular/hub pattern.
    """
    def __init__(self, unique_id, model):
        super().__init__(unique_id, model, is_fraud=True)
        self.target_hub = None

    def step(self):
        # Fraud agents transact more frequently
        if random.random() < 0.3:
            # Find another fraud agent to send money to (creating dense fraudulent clusters)
            fraud_agents = [a for a in self.model.users if a.is_fraud and a.unique_id != self.unique_id]
            if fraud_agents:
                target = self.random.choice(fraud_agents)
                amount = random.uniform(50, min(self.balance, 2000))
                self.balance -= amount
                target.balance += amount
                
                # Record transaction
                self.model.record_transaction(self.unique_id, target.unique_id, amount, is_fraud=True)
