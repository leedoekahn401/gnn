import sys
import os

# Ensure backend module can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.simulation.model import TransactionModel
from backend.db.neo4j_client import Neo4jClient

def main():
    print("Starting Mesa Simulation...")
    # Initialize the model with 500 normal users and 50 fraud users
    model = TransactionModel(num_normal=500, num_fraud=100)
    
    # Run simulation for 20 steps
    print("Running simulation steps...")
    for i in range(20):
        model.step()
        
    users = model.get_users()
    transactions = model.get_transactions()
    
    print(f"Generated {len(users)} users and {len(transactions)} transactions.")
    
    print("Connecting to Neo4j...")
    client = Neo4jClient()
    try:
        print("Creating constraints...")
        client.create_constraints()
        
        print("Clearing existing database...")
        client.clear_database()
        
        print("Inserting users into Neo4j...")
        # Batch insert users in chunks if necessary, but 550 is small enough for one go
        client.insert_users(users)
        
        print("Inserting transactions into Neo4j...")
        # Insert transactions
        client.insert_transactions(transactions)
        
        print("Successfully populated Neo4j database!")
    except Exception as e:
        print(f"Error connecting to or writing to Neo4j: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    main()
