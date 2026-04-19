# GraphGuard — Project Workflow Diagrams

## 1. High-Level System Architecture

```mermaid
graph TB
    subgraph Clients["🏢 Fintech Clients"]
        C1["Client App A"]
        C2["Client App B"]
    end

    subgraph API["⚡ FastAPI Service :8000"]
        AUTH["🔐 API Key Auth<br/>(SQLite)"]
        HASH["#️⃣ PII Hashing<br/>(SHA-256 + tenant salt)"]
        INGEST["POST /api/v1/ingest/transaction"]
        QUERY["GET /api/v1/alerts/fraudulent-users"]
        HEALTH["GET /health"]
    end

    subgraph Stream["📡 Apache Kafka"]
        TOPIC["Topic: raw_transactions"]
    end

    subgraph Worker["⚙️ Worker Service"]
        CONSUMER["Kafka Consumer"]
        WRITER["Neo4j Writer"]
    end

    subgraph Batch["⏰ Batch Scoring Service"]
        SCHEDULER["Periodic Scheduler<br/>(every N seconds)"]
        INFERENCE["GNN Batch Inference Engine"]
    end

    subgraph Storage["🗄️ Data Layer"]
        NEO4J[("Neo4j Graph DB<br/>:7474 / :7687")]
        SQLITE[("SQLite<br/>API Keys & Tenants")]
    end

    subgraph ML["🧠 GNN Engine"]
        MODEL["FraudGNNModel<br/>(GAT Conv × 2)"]
        CHECKPOINT["Model Checkpoints<br/>(v1, v2, ...)"]
    end

    C1 & C2 -->|"X-API-Key header"| AUTH
    AUTH --> INGEST
    AUTH --> QUERY
    INGEST --> HASH
    HASH -->|"Publish anonymized tx"| TOPIC
    TOPIC -->|"Consume messages"| CONSUMER
    CONSUMER --> WRITER
    WRITER -->|"MERGE nodes & edges"| NEO4J
    SCHEDULER -->|"Get unscored users"| NEO4J
    SCHEDULER --> INFERENCE
    INFERENCE -->|"Batch 2-hop neighborhoods"| NEO4J
    INFERENCE -->|"Load weights"| CHECKPOINT
    INFERENCE -->|"score > threshold → mark_fraud()"| NEO4J
    QUERY -->|"get_fraudulent_users()"| NEO4J
    AUTH -.->|"Verify key"| SQLITE

    style Clients fill:#1e293b,stroke:#3b82f6,color:#e2e8f0
    style API fill:#1e293b,stroke:#10b981,color:#e2e8f0
    style Stream fill:#1e293b,stroke:#f59e0b,color:#e2e8f0
    style Worker fill:#1e293b,stroke:#8b5cf6,color:#e2e8f0
    style Batch fill:#1e293b,stroke:#f472b6,color:#e2e8f0
    style Storage fill:#1e293b,stroke:#ef4444,color:#e2e8f0
    style ML fill:#1e293b,stroke:#ec4899,color:#e2e8f0
```

---

## 2. Phase 1 — Simulation & GNN Training Pipeline

```mermaid
flowchart LR
    subgraph Simulation["🎭 Mesa Simulation"]
        direction TB
        NORMAL["NormalAgent × 50<br/>Random txs, 10% chance"]
        FRAUD["FraudAgent × 10<br/>Circular txs, 30% chance"]
        TM["TransactionModel<br/>(step loop)"]
        NORMAL & FRAUD --> TM
    end

    subgraph Export["📤 Data Export"]
        USERS["get_users()<br/>id, is_fraud, balance"]
        TXS["get_transactions()<br/>tx_id, source, target,<br/>amount, timestamp, is_fraud"]
    end

    subgraph GraphDB["🗄️ Neo4j"]
        INSERT_U["insert_users()"]
        INSERT_T["insert_transactions()"]
        GRAPH[("Graph<br/>:User nodes<br/>:TRANSACTED edges")]
    end

    subgraph Training["🧠 GNN Training"]
        DATASET["FraudGraphDataset<br/>(load from Neo4j)"]
        SPLIT["Train / Val / Test<br/>mask split"]
        TRAIN_LOOP["Training Loop<br/>(100 epochs, Adam)"]
        EVAL["Evaluation<br/>F1, Precision, Recall, AUC"]
        SAVE["💾 Save Checkpoint<br/>fraud_gnn_model_v1.pth"]
    end

    TM --> USERS & TXS
    USERS --> INSERT_U --> GRAPH
    TXS --> INSERT_T --> GRAPH
    GRAPH --> DATASET --> SPLIT --> TRAIN_LOOP --> EVAL --> SAVE

    style Simulation fill:#0f172a,stroke:#3b82f6,color:#e2e8f0
    style Export fill:#0f172a,stroke:#06b6d4,color:#e2e8f0
    style GraphDB fill:#0f172a,stroke:#ef4444,color:#e2e8f0
    style Training fill:#0f172a,stroke:#a855f7,color:#e2e8f0
```

---

## 3. Phase 2 — Transaction Ingestion & Batch Fraud Scoring

### 3a. Transaction Ingestion (Write Path)

```mermaid
sequenceDiagram
    participant Client as 🏢 Client
    participant API as ⚡ FastAPI
    participant SQLite as 🔑 SQLite
    participant Kafka as 📡 Kafka
    participant Worker as ⚙️ Worker
    participant Neo4j as 🗄️ Neo4j

    Client->>API: POST /api/v1/ingest/transaction<br/>(X-API-Key header + body)
    API->>SQLite: Verify API Key
    SQLite-->>API: ✅ tenant_id, name

    Note over API: Hash source & target IDs<br/>SHA-256(tenant_id::graphguard::raw_id)

    API->>Kafka: Publish to "raw_transactions"<br/>{tenant_id, anonymized_tx}
    API-->>Client: 200 OK — "Transaction securely<br/>anonymized and queued."

    Note over Kafka,Worker: Async processing

    Kafka->>Worker: Consume message
    Worker->>Neo4j: MERGE User nodes & TRANSACTED edge<br/>(multi-tenant isolation)
    Note over Worker: ✅ Write only — bumps last_tx_at on users
```

### 3b. Batch Fraud Scoring (Scoring Path)

> **Re-scoring logic:** A user is picked up for scoring if `last_scored_at IS NULL`
> (never scored) **or** `last_tx_at > last_scored_at` (new transactions arrived since
> last score). This means a previously-clean user **will** be re-evaluated when
> new suspicious activity occurs.

```mermaid
sequenceDiagram
    participant Scheduler as ⏰ Batch Scheduler
    participant Neo4j as 🗄️ Neo4j
    participant GNN as 🧠 GNN Model

    loop Every BATCH_INTERVAL_SECONDS (default: 60s)
        Scheduler->>Neo4j: get_unscored_users(limit)<br/>WHERE last_scored_at IS NULL<br/>OR last_tx_at > last_scored_at
        Neo4j-->>Scheduler: [{user_id, tenant_id}, ...] (batch)

        alt Users needing (re-)scoring found
            loop For each user in batch
                Scheduler->>Neo4j: get_neighborhood(user_id, tenant, hops=2)
                Neo4j-->>Scheduler: Subgraph {nodes, edges}
                Scheduler->>GNN: predict(subgraph, user_id)
                GNN-->>Scheduler: fraud_probability

                alt fraud_prob > 0.7
                    Scheduler->>Neo4j: mark_fraud(user_id, tenant, score)<br/>SET last_scored_at = now()
                    Note over Scheduler: 🚨 FRAUD DETECTED
                else fraud_prob ≤ 0.7
                    Scheduler->>Neo4j: mark_scored(user_id, tenant, score)<br/>SET last_scored_at = now()
                    Note over Scheduler: ✅ Clean — will re-score on new txs
                end
            end
        else No users to score
            Note over Scheduler: 💤 Nothing to score, sleeping...
        end
    end
```

---

## 4. Phase 2 — Fraud Query Flow

```mermaid
sequenceDiagram
    participant Client as 🏢 Client
    participant API as ⚡ FastAPI
    participant SQLite as 🔑 SQLite
    participant Neo4j as 🗄️ Neo4j

    Client->>API: GET /api/v1/alerts/fraudulent-users<br/>(X-API-Key header, ?limit=10)
    API->>SQLite: Verify API Key
    SQLite-->>API: ✅ tenant_id, name

    API->>Neo4j: get_fraudulent_users(tenant_id, limit)
    Note over Neo4j: MATCH (u:User {tenant_id, is_fraud: true})<br/>ORDER BY fraud_score DESC

    Neo4j-->>API: [{hashed_user_id, balance, fraud_score}, ...]
    API-->>Client: 200 OK<br/>{tenant, fraud_users: [...]}
```

---

## 5. Docker Services & Dependencies

```mermaid
graph TB
    NEO4J["🗄️ neo4j:latest<br/>Container: neo4j_db<br/>Ports: 7474, 7687"]
    KAFKA["📡 bitnamilegacy/kafka:latest<br/>Container: kafka_broker<br/>Ports: 9092, 29092"]
    API_SVC["⚡ graphguard_api<br/>uvicorn api.main:app<br/>Port: 8000"]
    WORKER_SVC["⚙️ graphguard_worker<br/>python -m worker.consumer"]
    VOLUMES["📁 Volumes<br/>neo4j_data, neo4j_logs"]

    API_SVC -->|"depends_on: healthy"| KAFKA
    API_SVC -->|"depends_on: healthy"| NEO4J
    WORKER_SVC -->|"depends_on: healthy"| KAFKA
    WORKER_SVC -->|"depends_on: healthy"| NEO4J
    NEO4J --> VOLUMES

    style NEO4J fill:#1e293b,stroke:#ef4444,color:#e2e8f0
    style KAFKA fill:#1e293b,stroke:#f59e0b,color:#e2e8f0
    style API_SVC fill:#1e293b,stroke:#10b981,color:#e2e8f0
    style WORKER_SVC fill:#1e293b,stroke:#8b5cf6,color:#e2e8f0
    style VOLUMES fill:#1e293b,stroke:#6b7280,color:#e2e8f0
```

---

## Key File Mapping

| Component | Key Files |
|---|---|
| **API Service** | [main.py](file:///c:/Document/fraud-detech/backend/api/main.py), [security.py](file:///c:/Document/fraud-detech/backend/api/security.py), [schemas.py](file:///c:/Document/fraud-detech/backend/api/schemas.py) |
| **API Routers** | [ingest.py](file:///c:/Document/fraud-detech/backend/api/routers/ingest.py), [query.py](file:///c:/Document/fraud-detech/backend/api/routers/query.py) |
| **Worker** | [consumer.py](file:///c:/Document/fraud-detech/backend/worker/consumer.py) |
| **Database** | [neo4j_client.py](file:///c:/Document/fraud-detech/backend/db/neo4j_client.py), [init_db.py](file:///c:/Document/fraud-detech/backend/api/init_db.py) |
| **GNN Engine** | [model.py](file:///c:/Document/fraud-detech/backend/gnn/model.py), [train.py](file:///c:/Document/fraud-detech/backend/gnn/train.py), [inference.py](file:///c:/Document/fraud-detech/backend/gnn/inference.py) |
| **Simulation** | [model.py](file:///c:/Document/fraud-detech/backend/simulation/model.py), [agents.py](file:///c:/Document/fraud-detech/backend/simulation/agents.py) |
| **Infrastructure** | [docker-compose.yaml](file:///c:/Document/fraud-detech/backend/docker-compose.yaml), [Dockerfile](file:///c:/Document/fraud-detech/backend/Dockerfile) |
