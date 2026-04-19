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

    # =========================================================================
    # Phase 1 Methods (Simulation — no tenant isolation)
    # =========================================================================

    def create_constraints(self):
        with self.driver.session() as session:
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
        batch_size = 5
        with self.driver.session() as session:
            for i in range(0, len(users), batch_size):
                batch = users[i:i + batch_size]
                session.run(query, users=batch)

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
        batch_size = 5
        with self.driver.session() as session:
            for i in range(0, len(transactions), batch_size):
                batch = transactions[i:i + batch_size]
                session.run(query, transactions=batch)

    # =========================================================================
    # Phase 2 Methods (Multi-tenant — tenant_id isolation)
    # =========================================================================

    def insert_transaction_multitenant(self, tx: dict, tenant_id: str):
        """
        Insert a single transaction into Neo4j with tenant isolation.
        
        - MERGE source and target User nodes with tenant_id
        - Create TRANSACTED relationship with transaction properties
        - Bumps last_tx_at on both users so the batch scorer knows
          there is new activity to evaluate
        """
        query = """
        MERGE (s:User {id: $source, tenant_id: $tenant_id})
        ON CREATE SET s.balance = 0.0, s.is_fraud = false,
                      s.fraud_score = 0.0, s.last_scored_at = null
        SET s.last_tx_at = datetime()
        MERGE (t:User {id: $target, tenant_id: $tenant_id})
        ON CREATE SET t.balance = 0.0, t.is_fraud = false,
                      t.fraud_score = 0.0, t.last_scored_at = null
        SET t.last_tx_at = datetime()
        MERGE (s)-[r:TRANSACTED {tx_id: $tx_id}]->(t)
        SET r.amount = $amount,
            r.timestamp = $timestamp,
            r.tenant_id = $tenant_id
        """
        with self.driver.session() as session:
            session.run(
                query,
                source=tx["source"],
                target=tx["target"],
                tx_id=tx["tx_id"],
                amount=tx["amount"],
                timestamp=tx["timestamp"],
                tenant_id=tenant_id,
            )

    def get_neighborhood(self, user_hash: str, tenant_id: str, hops: int = 2) -> dict:
        """
        Return the subgraph around a user node (up to `hops` hops away).
        
        Returns:
            dict with:
                - "nodes": list of {"id": str, "balance": float}
                - "edges": list of {"source": str, "target": str, "amount": float}
        """
        query = """
        MATCH path = (center:User {id: $user_id, tenant_id: $tenant_id})-[:TRANSACTED*1..$hops]-(neighbor)
        WHERE neighbor.tenant_id = $tenant_id
        WITH nodes(path) AS ns, relationships(path) AS rs
        UNWIND ns AS n
        WITH COLLECT(DISTINCT n) AS all_nodes, rs
        UNWIND rs AS r
        WITH all_nodes, COLLECT(DISTINCT r) AS all_rels
        RETURN
            [n IN all_nodes | {id: n.id, balance: COALESCE(n.balance, 0.0)}] AS nodes,
            [r IN all_rels  | {source: startNode(r).id, target: endNode(r).id, amount: COALESCE(r.amount, 0.0)}] AS edges
        """
        with self.driver.session() as session:
            result = session.run(query, user_id=user_hash, tenant_id=tenant_id, hops=hops)
            record = result.single()
            if record:
                return {"nodes": record["nodes"], "edges": record["edges"]}
            return {"nodes": [], "edges": []}

    def mark_fraud(self, user_hash: str, tenant_id: str, fraud_score: float = 1.0):
        """Mark a user node as fraudulent with a fraud score and record scoring time."""
        query = """
        MATCH (u:User {id: $user_id, tenant_id: $tenant_id})
        SET u.is_fraud = true,
            u.fraud_score = $fraud_score,
            u.last_scored_at = datetime()
        """
        with self.driver.session() as session:
            session.run(query, user_id=user_hash, tenant_id=tenant_id, fraud_score=fraud_score)

    def get_unscored_users(self, limit: int = 100) -> list[dict]:
        """
        Return users that need (re-)scoring by the batch GNN scorer.
        
        A user needs scoring if:
          1. They have never been scored (last_scored_at IS NULL), OR
          2. They have new transactions since their last scoring
             (last_tx_at > last_scored_at)
        
        This ensures that a previously-clean user who receives new
        suspicious transactions will be re-evaluated.
        
        Returns a list of {user_id, tenant_id} dicts.
        """
        query = """
        MATCH (u:User)
        WHERE u.last_scored_at IS NULL
           OR u.last_tx_at > u.last_scored_at
        RETURN u.id AS user_id, u.tenant_id AS tenant_id
        ORDER BY u.last_scored_at ASC
        LIMIT $limit
        """
        results = []
        with self.driver.session() as session:
            records = session.run(query, limit=limit)
            for record in records:
                results.append({
                    "user_id": record["user_id"],
                    "tenant_id": record["tenant_id"],
                })
        return results

    def mark_scored(self, user_hash: str, tenant_id: str, fraud_score: float):
        """Mark a user as scored (not fraudulent) and record the timestamp."""
        query = """
        MATCH (u:User {id: $user_id, tenant_id: $tenant_id})
        SET u.fraud_score = $fraud_score,
            u.last_scored_at = datetime()
        """
        with self.driver.session() as session:
            session.run(query, user_id=user_hash, tenant_id=tenant_id, fraud_score=fraud_score)

    def get_fraudulent_users(self, tenant_id: str, limit: int = 10) -> list[dict]:
        """Query users flagged as fraudulent for a given tenant."""
        query = """
        MATCH (u:User {tenant_id: $tenant_id, is_fraud: true})
        RETURN u.id AS hashed_user_id, 
               u.balance AS balance,
               u.fraud_score AS fraud_score
        ORDER BY u.fraud_score DESC
        LIMIT $limit
        """
        results = []
        with self.driver.session() as session:
            records = session.run(query, tenant_id=tenant_id, limit=limit)
            for record in records:
                results.append({
                    "hashed_user_id": record["hashed_user_id"],
                    "balance": record["balance"],
                    "fraud_score": record["fraud_score"],
                })
        return results
