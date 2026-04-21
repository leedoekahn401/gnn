import sys
import os
import random

# Ensure backend module can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.simulation.model import TransactionModel
from backend.db.neo4j_client import Neo4jClient

def main():
    print("🚀 Reseeding Neo4j with small sample...")
    
    # We want ~100 nodes and ~200 transactions.
    # The TransactionModel creates agents and then runs steps.
    # To get 100 nodes, we initialize with 100 agents.
    model = TransactionModel(num_normal=80, num_fraud=20)
    
    # We want exactly 200 transactions. 
    # The model's step() generates random transactions.
    # Instead of running fixed steps, we can manually trigger transactions 
    # or run until we hit the count.
    
    print("Running simulation to generate transactions...")
    target_tx = 200
    while len(model.get_transactions()) < target_tx:
        model.step()
    
    users = model.get_users()[:100] # Ensure exactly 100 users
    transactions = model.get_transactions()[:200] # Ensure exactly 200 transactions
    
    print(f"Generated {len(users)} users and {len(transactions)} transactions.")
    
    client = Neo4jClient()
    try:
        print("Creating constraints...")
        client.create_constraints()
        
        print("🧹 Clearing existing database...")
        client.clear_database()
        
        print("📥 Inserting users into Neo4j...")
        client.insert_users(users)
        
        print("📥 Inserting transactions into Neo4j...")
        client.insert_transactions(transactions)
        
        print("✅ Successfully reseeded database with 100 nodes and 200 edges!")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    main()
