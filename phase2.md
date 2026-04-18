Backend Architecture & API Specifications
Phase 2: Backend & API Development (Multi-tenant SaaS)1. System Architecture OverviewGraphGuard utilizes an Event-Driven Microservices Architecture to separate high-throughput data ingestion from heavy Graph Neural Network (GNN) inference.
Sơ đồ luồng dữ liệu (Data Flow)
  flowchart TD
    Client([Fintech Startup Client])

    subgraph GraphGuard SaaS Architecture
        API[API Service <br/> FastAPI]
        Kafka[[Kafka Message Broker <br/> Topic: raw_transactions]]
        Worker[Worker Service <br/> Kafka Consumer + GNN Model]
        Neo4j[(Neo4j Graph Database)]
    end

    %% Ingestion Flow
    Client -- "1. POST /api/v1/ingest/transaction" --> API
    API -- "2. Hash PII & Produce message" --> Kafka
    Kafka -- "3. Consume message (Background)" --> Worker
    Worker -- "4. Save Graph & Run GNN Inference" --> Neo4j

    %% Query Flow
    Client -. "5. GET /api/v1/alerts/fraudulent-users" .-> API
    API -. "6. Query Fraudulent Nodes" .-> Neo4j
2. Core PrinciplesMulti-tenancy (Logical Separation): All data in Neo4j is segregated using a tenant_id property on nodes and edges.Zero-Knowledge Data Pseudonymization: The system does NOT store plain-text User IDs. source and target IDs are hashed using SHA-256 combined with the tenant_id as a salt at the API layer before entering the database or Kafka.Decoupling: API Service only handles authentication, hashing, and Kafka publishing. Worker Service handles Neo4j I/O and PyTorch GNN execution.

3. Directory Structure
backend/
├── docker-compose.yaml
├── pyproject.toml
├── api/
│   ├── main.py
│   ├── schemas.py
│   ├── security.py
│   ├── dependencies.py
│   └── routers/
│       ├── ingest.py
│       └── query.py
├── worker/
│   └── consumer.py
├── db/
│   └── neo4j_client.py
└── gnn/
    └── checkpoints/
4. Infrastructure (docker-compose.yaml)version: '3.8'

services:
  neo4j:
    image: neo4j:latest
    container_name: neo4j_db
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      - NEO4J_AUTH=neo4j/password123
      - NEO4J_PLUGINS=["apoc"]
    volumes:
      - neo4j_data:/data

  kafka:
    image: bitnami/kafka:latest
    container_name: kafka_broker
    ports:
      - "9092:9092"
    environment:
      - KAFKA_CFG_NODE_ID=1
      - KAFKA_CFG_PROCESS_ROLES=broker,controller
      - KAFKA_CFG_CONTROLLER_QUORUM_VOTERS=1@kafka:9093
      - KAFKA_CFG_LISTENERS=PLAINTEXT://:9092,CONTROLLER://:9093
      - KAFKA_CFG_ADVERTISED_LISTENERS=PLAINTEXT://kafka:9092
      - KAFKA_CFG_CONTROLLER_LISTENER_NAMES=CONTROLLER
      - ALLOW_PLAINTEXT_LISTENER=yes

  api_service:
    build: .
    command: uvicorn api.main:app --host 0.0.0.0 --port 8000
    depends_on:
      - kafka
      - neo4j
    environment:
      - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
      - NEO4J_URI=bolt://neo4j:7687
    ports:
      - "8000:8000"

  worker_service:
    build: .
    command: python worker/consumer.py
    depends_on:
      - kafka
      - neo4j
    environment:
      - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
      - NEO4J_URI=bolt://neo4j:7687

volumes:
  neo4j_data:
5. API Implementation Details5.1 Security & Hashing (api/security.py)import hashlib
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

# Mocked DB for valid API keys
VALID_API_KEYS = {
    "sk_live_abc123": {"tenant_id": "startup_a", "name": "Alpha Fintech"}
}

def verify_api_key(api_key: str = Security(api_key_header)):
    client_info = VALID_API_KEYS.get(api_key)
    if not client_info:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return client_info

def hash_node_id(tenant_id: str, raw_id: str) -> str:
    """Hash ID to protect PII. Use tenant_id as salt."""
    payload = f"{tenant_id}::graphguard::{raw_id}"
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()
5.2 Schemas (api/schemas.py)from pydantic import BaseModel, Field

class TransactionInput(BaseModel):
    tx_id: str = Field(..., description="Unique Transaction ID")
    source: str = Field(..., description="Sender User ID (Plain text)")
    target: str = Field(..., description="Receiver User ID (Plain text)")
    amount: float = Field(..., gt=0)
    timestamp: int = Field(...)
5.3 Dependencies (api/dependencies.py)from aiokafka import AIOKafkaProducer
from db.neo4j_client import Neo4jClient

kafka_producer: AIOKafkaProducer = None
neo4j_client = Neo4jClient()
KAFKA_TOPIC = "raw_transactions"

def get_kafka_producer(): return kafka_producer
def get_neo4j_client(): return neo4j_client
5.4 Ingestion Router (api/routers/ingest.py)from fastapi import APIRouter, Depends
from aiokafka import AIOKafkaProducer
from api.schemas import TransactionInput
from api.dependencies import get_kafka_producer, KAFKA_TOPIC
from api.security import verify_api_key, hash_node_id

router = APIRouter(prefix="/api/v1/ingest", tags=["Ingestion"])

@router.post("/transaction")
async def ingest_transaction(
    tx: TransactionInput,
    client_info: dict = Depends(verify_api_key),
    producer: AIOKafkaProducer = Depends(get_kafka_producer)
):
    tenant_id = client_info["tenant_id"]
    
    # Anonymize data (Zero-Knowledge)
    anonymized_tx = {
        "tx_id": tx.tx_id,
        "source": hash_node_id(tenant_id, tx.source),
        "target": hash_node_id(tenant_id, tx.target),
        "amount": tx.amount,
        "timestamp": tx.timestamp
    }
    
    message = {"tenant_id": tenant_id, "transaction": anonymized_tx}
    await producer.send_and_wait(KAFKA_TOPIC, message)
    
    return {"status": "success", "message": "Transaction securely anonymized and queued."}
5.5 Query Router (api/routers/query.py)from fastapi import APIRouter, Depends
from api.dependencies import get_neo4j_client
from api.security import verify_api_key

router = APIRouter(prefix="/api/v1/alerts", tags=["Alerts"])

@router.get("/fraudulent-users")
def get_fraudulent_users(limit: int = 10, client_info: dict = Depends(verify_api_key)):
    neo4j_db = get_neo4j_client()
    query = """
    MATCH (u:User {tenant_id: $tenant_id, is_fraud: true})
    RETURN u.id AS hashed_user_id, u.balance AS balance
    LIMIT $limit
    """
    results = []
    with neo4j_db.driver.session() as session:
        records = session.run(query, tenant_id=client_info["tenant_id"], limit=limit)
        for record in records:
            results.append({"hashed_user_id": record["hashed_user_id"], "balance": record["balance"]})
            
    return {"tenant": client_info["name"], "fraud_users": results}
5.6 Main Setup (api/main.py)import os, json
from contextlib import asynccontextmanager
from fastapi import FastAPI
from aiokafka import AIOKafkaProducer
import api.dependencies as deps
from api.routers import ingest, query

@asynccontextmanager
async def lifespan(app: FastAPI):
    deps.kafka_producer = AIOKafkaProducer(
        bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    await deps.kafka_producer.start()
    yield
    await deps.kafka_producer.stop()
    deps.neo4j_client.close()

app = FastAPI(title="GraphGuard API", lifespan=lifespan)
app.include_router(ingest.router)
app.include_router(query.router)
6. Worker Service Implementation (worker/consumer.py)import os, json, asyncio
from aiokafka import AIOKafkaConsumer
from db.neo4j_client import Neo4jClient
# from gnn.model import GraphGuardGNN # Future implementation

async def consume():
    neo4j_db = Neo4jClient()
    consumer = AIOKafkaConsumer(
        "raw_transactions",
        bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        group_id="graphguard_gnn_group"
    )
    await consumer.start()
    print("[Worker] Listening to Kafka...")
    
    try:
        async for msg in consumer:
            data = msg.value
            tenant_id = data.get("tenant_id")
            tx = data.get("transaction") # Note: source and target are already hashed here
            
            # 1. Update Neo4j 
            # Note: Neo4jClient's insert_transactions MUST be updated to accept tenant_id
            neo4j_db.insert_transactions([tx], tenant_id)
            
            # 2. Trigger GNN Inference
            # subgraph = neo4j_db.get_neighborhood(tx['source'], tenant_id)
            # is_fraud = gnn_model.predict(subgraph)
            # if is_fraud: neo4j_db.mark_fraud(tx['source'], tenant_id)
            
    finally:
        await consumer.stop()
        neo4j_db.close()

if __name__ == "__main__":
    asyncio.run(consume())
