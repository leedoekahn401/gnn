import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

class Neo4jClient:
    def __init__(self):
        load_dotenv()
        self.uri = os.getenv("NEO4J_URI")
        self.user = os.getenv("NEO4J_USERNAME")
        self.password = os.getenv("NEO4J_PASSWORD")
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    def close(self):
        self.driver.close()

    def create_constraints(self):
        with self.driver.session() as session:
            # Drop constraint if exists (neo4j syntax varies, we'll just try to create for now, ignoring error if exists)
            try:
                session.run("CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE")
            except Exception as e:
                print(f"Constraint creation warning: {e}")

    def clear_database(self):
        """Clears all nodes and relationships (use with caution!)"""
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    def insert_users(self, users):
        query = """
        UNWIND $users AS user
        MERGE (u:User {id: user.id})
        SET u.is_fraud = user.is_fraud, u.balance = user.balance
        """
        with self.driver.session() as session:
            session.run(query, users=users)

    def insert_transactions(self, transactions):
        query = """
        UNWIND $transactions AS tx
        MATCH (s:User {id: tx.source})
        MATCH (t:User {id: tx.target})
        MERGE (s)-[r:TRANSACTED {tx_id: tx.tx_id}]->(t)
        SET r.amount = tx.amount,
            r.timestamp = tx.timestamp,
            r.is_fraud = tx.is_fraud,
            r.step = tx.step
        """
        with self.driver.session() as session:
            session.run(query, transactions=transactions)
