# 🛡️ GraphGuard — Graph-Based Fraud Detection SaaS

A multi-tenant fraud detection backend that combines **Graph Neural Networks (GNN)** with **Neo4j graph storage** to identify fraudulent transaction patterns in real time. Fintech clients submit transactions via REST API — GraphGuard anonymizes, stores, and scores them using a trained GAT model.

---

## Architecture Overview

```
Client → FastAPI (auth + hash PII) → Kafka → Worker (write to Neo4j)
                                                  ↓
                                          Batch Scorer (periodic)
                                                  ↓
                                      GNN Inference → mark fraud/clean
                                                  ↓
Client ← FastAPI ← Query fraudulent users ← Neo4j
```

### Core Components

| Service | Description | Port |
|---|---|---|
| **FastAPI API** | REST API — ingests transactions, serves fraud alerts | `8000` |
| **Kafka** | Message queue for async transaction processing | `9092` / `29092` |
| **Worker** | Consumes Kafka messages, writes to Neo4j | — |
| **Batch Scorer** | Periodic GNN inference on unscored/stale users | — |
| **Neo4j** | Graph database storing users & transaction edges | `7474` / `7687` |
| **SQLite** | Stores API keys and tenant metadata | — |

### Data Flow

1. **Ingest** — Client sends `POST /api/v1/ingest/transaction` with an API key
2. **Anonymize** — API hashes user IDs with SHA-256 (`tenant_id::graphguard::raw_id`)
3. **Queue** — Anonymized transaction published to Kafka topic `raw_transactions`
4. **Write** — Worker consumes message, MERGEs user nodes + TRANSACTED edge into Neo4j
5. **Score** — Batch scorer periodically finds unscored users (or users with new activity), fetches their 2-hop neighborhood, and runs GNN inference
6. **Alert** — Users exceeding the fraud threshold are flagged; clients query them via `GET /api/v1/alerts/fraudulent-users`

### Batch Re-Scoring Logic

Users are picked up for scoring when:
- `last_scored_at IS NULL` — never scored before, **or**
- `last_tx_at > last_scored_at` — new transactions arrived since last score

This ensures previously-clean users are **re-evaluated** when new suspicious activity occurs.

---

## Project Structure

```
backend/
├── api/                          # FastAPI application
│   ├── main.py                   # App entrypoint, lifespan, health check
│   ├── dependencies.py           # Kafka producer & Neo4j client singletons
│   ├── init_db.py                # SQLite schema + default API key seeding
│   ├── schemas.py                # Pydantic request/response models
│   ├── security.py               # API key auth + PII hashing
│   └── routers/
│       ├── ingest.py             # POST /api/v1/ingest/transaction
│       └── query.py              # GET /api/v1/alerts/fraudulent-users
├── worker/
│   └── consumer.py               # Kafka consumer (write path) + batch scorer
├── db/
│   └── neo4j_client.py           # Neo4j driver wrapper (Phase 1 + Phase 2 methods)
├── gnn/
│   ├── model.py                  # FraudGNNModel (GAT Conv × 2)
│   ├── dataset.py                # FraudGraphDataset (loads graph from Neo4j)
│   ├── inference.py              # FraudInferenceEngine (subgraph → fraud probability)
│   ├── train.py                  # Training script with versioned checkpoints
│   └── checkpoints/              # Saved model weights (v1, v2, ...)
├── simulation/
│   ├── model.py                  # Mesa TransactionModel
│   └── agents.py                 # NormalAgent + FraudAgent
├── tests/
│   ├── conftest.py               # Shared fixtures (mocked Kafka, Neo4j, SQLite)
│   ├── test_health.py            # Health endpoint tests
│   ├── test_ingest.py            # Ingestion endpoint tests
│   ├── test_query.py             # Fraud query endpoint tests
│   └── test_security.py          # Auth & PII hashing tests
├── docker-compose.yaml           # Neo4j + Kafka + API + Worker services
├── Dockerfile                    # Python 3.12 container image
├── pyproject.toml                # Dependencies & project metadata
├── run_simulation.py             # Script to populate Neo4j with simulated data
├── .env                          # Local dev environment variables
└── graphguard_workflow.md        # Architecture diagrams (Mermaid)
```

---

## Getting Started

### Prerequisites

- **Python 3.12+**
- **Docker & Docker Compose** (for Neo4j + Kafka)
- **uv** (recommended) or pip for dependency management

### 1. Start Infrastructure

```bash
docker compose up -d
```

This starts:
- **Neo4j** on `localhost:7474` (browser) / `localhost:7687` (bolt)
- **Kafka** on `localhost:29092` (external) / `localhost:9092` (internal)

Wait for health checks to pass:

```bash
docker compose ps   # All services should show "healthy"
```

### 2. Install Dependencies

```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -e ".[dev]"
```

### 3. Configure Environment

The `.env` file is pre-configured for local development:

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=password123
KAFKA_BOOTSTRAP_SERVERS=localhost:29092
GNN_MODEL_VERSION=v1
GNN_CHECKPOINT_DIR=gnn/checkpoints
FRAUD_THRESHOLD=0.7
SQLITE_DB_PATH=data/graphguard.db
```

---

## Phase 1 — Simulation & GNN Training

### Step 1: Run the Simulation

Generates synthetic users and transactions, then populates Neo4j:

```bash
python run_simulation.py
```

This creates **500 normal users** + **100 fraud agents** running for 20 steps, producing a graph of `:User` nodes connected by `:TRANSACTED` edges.

### Step 2: Train the GNN

```bash
python -m gnn.train --save_version v1 --epochs 100
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--save_version` | `v1` | Version tag for the checkpoint file |
| `--load_version` | `None` | Resume training from an existing checkpoint |
| `--epochs` | `100` | Number of training epochs |

The model (2-layer GAT with edge attributes) is saved to `gnn/checkpoints/fraud_gnn_model_v1.pth`.

**Output metrics:** F1, Precision, Recall, AUC-ROC on the test set.

---

## Phase 2 — Running the SaaS Backend

### Start the API Server

```bash
uvicorn api.main:app --reload --port 8000
```

### Start the Worker (Consumer + Batch Scorer)

In a separate terminal:

```bash
python -m worker.consumer
```

The worker runs two concurrent tasks:
- **Consumer** — Listens on Kafka, writes transactions to Neo4j
- **Batch Scorer** — Every 60s, scores unscored/stale users via GNN inference

### API Endpoints

#### Health Check

```bash
curl http://localhost:8000/health
```

```json
{"status": "ok", "service": "graphguard-api"}
```

#### Ingest a Transaction

```bash
curl -X POST http://localhost:8000/api/v1/ingest/transaction \
  -H "X-API-Key: sk_live_abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "tx_id": "tx_001",
    "source": "alice",
    "target": "bob",
    "amount": 500.00,
    "timestamp": 1713400000
  }'
```

```json
{"status": "success", "message": "Transaction securely anonymized and queued."}
```

> **Note:** `source` and `target` are plain-text user IDs. The API hashes them with SHA-256 before storing — the raw IDs never reach the database.

#### Query Fraudulent Users

```bash
curl http://localhost:8000/api/v1/alerts/fraudulent-users?limit=5 \
  -H "X-API-Key: sk_live_abc123"
```

```json
{
  "tenant": "Alpha Fintech",
  "fraud_users": [
    {"hashed_user_id": "a3f8c...", "balance": 0.0, "fraud_score": 0.92},
    {"hashed_user_id": "7b2e1...", "balance": 0.0, "fraud_score": 0.85}
  ]
}
```

### Default API Key

A development key is seeded on startup:

| Key | Tenant ID | Tenant Name |
|---|---|---|
| `sk_live_abc123` | `startup_a` | Alpha Fintech |

---

## Running with Docker Compose (Full Stack)

To run everything — Neo4j, Kafka, API, and Worker — in containers:

```bash
docker compose up --build
```

| Container | Command | Port |
|---|---|---|
| `neo4j_db` | Neo4j server | `7474`, `7687` |
| `kafka_broker` | KRaft-mode Kafka | `9092`, `29092` |
| `graphguard_api` | `uvicorn api.main:app` | `8000` |
| `graphguard_worker` | `python -m worker.consumer` | — |

### Worker Environment Variables

| Variable | Default | Description |
|---|---|---|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:29092` | Kafka broker address |
| `NEO4J_URI` | — | Neo4j bolt URI |
| `NEO4J_USERNAME` | — | Neo4j username |
| `NEO4J_PASSWORD` | — | Neo4j password |
| `GNN_MODEL_VERSION` | `v1` | Which checkpoint version to load |
| `GNN_CHECKPOINT_DIR` | `gnn/checkpoints` | Path to checkpoint directory |
| `FRAUD_THRESHOLD` | `0.7` | Probability threshold to flag fraud |
| `BATCH_INTERVAL_SECONDS` | `60` | Seconds between batch scoring runs |
| `BATCH_SIZE` | `100` | Max users to score per batch cycle |

---

## Testing

Tests use mocked Kafka and Neo4j — no external services required.

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run a specific test file
pytest tests/test_ingest.py
```

### Test Coverage

| Test File | What it covers |
|---|---|
| `test_health.py` | Health endpoint |
| `test_ingest.py` | Transaction ingestion, PII hashing, Kafka publishing |
| `test_query.py` | Fraud alert queries, tenant isolation |
| `test_security.py` | API key authentication, invalid/inactive keys |

---

## Tech Stack

| Layer | Technology |
|---|---|
| **API Framework** | FastAPI + Uvicorn |
| **Message Queue** | Apache Kafka (via aiokafka) |
| **Graph Database** | Neo4j |
| **GNN Framework** | PyTorch + PyTorch Geometric (GATConv) |
| **Simulation** | Mesa 3.x (Agent-Based Modeling) |
| **Auth Store** | SQLite |
| **Testing** | pytest + httpx |
| **Containerization** | Docker + Docker Compose |

---

## License

Private — Internal use only.
