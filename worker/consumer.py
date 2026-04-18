"""
GraphGuard Worker Service — Kafka Consumer + Neo4j Writer + GNN Inference.

Consumes anonymized transactions from Kafka, writes them to Neo4j,
runs GNN inference on the source node's neighborhood, and flags fraud.

Usage:
    python -m worker.consumer

Environment Variables:
    KAFKA_BOOTSTRAP_SERVERS  - Kafka broker address (default: localhost:29092)
    NEO4J_URI               - Neo4j bolt URI
    NEO4J_USERNAME          - Neo4j username
    NEO4J_PASSWORD          - Neo4j password
    GNN_MODEL_VERSION       - Model checkpoint version to load (default: v1)
    GNN_CHECKPOINT_DIR      - Directory containing model checkpoints (default: gnn/checkpoints)
    FRAUD_THRESHOLD         - Probability threshold to flag fraud (default: 0.7)
"""

import os
import json
import asyncio
import signal
import sys

from aiokafka import AIOKafkaConsumer
from db.neo4j_client import Neo4jClient
from gnn.inference import FraudInferenceEngine

# --- Configuration ---
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
KAFKA_TOPIC = "raw_transactions"
KAFKA_GROUP = "graphguard_gnn_group"

GNN_MODEL_VERSION = os.getenv("GNN_MODEL_VERSION", "v1")
GNN_CHECKPOINT_DIR = os.getenv("GNN_CHECKPOINT_DIR", "gnn/checkpoints")
FRAUD_THRESHOLD = float(os.getenv("FRAUD_THRESHOLD", "0.7"))

# Graceful shutdown flag
shutdown_event = asyncio.Event()


def _handle_signal():
    print("\n[Worker] Shutdown signal received. Finishing current message...")
    shutdown_event.set()


async def consume():
    """Main consumer loop."""
    neo4j_db = Neo4jClient()

    # Load GNN inference engine
    checkpoint_path = os.path.join(GNN_CHECKPOINT_DIR, f"fraud_gnn_model_{GNN_MODEL_VERSION}.pth")
    gnn_engine = None
    if os.path.exists(checkpoint_path):
        gnn_engine = FraudInferenceEngine(checkpoint_path)
        print(f"[Worker] ✅ GNN model loaded: version '{GNN_MODEL_VERSION}' from {checkpoint_path}")
    else:
        print(f"[Worker] ⚠️  GNN checkpoint not found at {checkpoint_path}. Running without inference.")

    consumer = AIOKafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        group_id=KAFKA_GROUP,
        auto_offset_reset="earliest",
    )

    await consumer.start()
    print(f"[Worker] 🎧 Listening on topic '{KAFKA_TOPIC}' (group: {KAFKA_GROUP})...")

    try:
        async for msg in consumer:
            if shutdown_event.is_set():
                break

            data = msg.value
            tenant_id = data.get("tenant_id")
            tx = data.get("transaction")

            if not tenant_id or not tx:
                print(f"[Worker] ⚠️  Malformed message, skipping: {data}")
                continue

            # 1. Write transaction to Neo4j (multi-tenant)
            try:
                neo4j_db.insert_transaction_multitenant(tx, tenant_id)
                print(
                    f"[Worker] 📝 Saved tx {tx['tx_id'][:8]}... "
                    f"({tx['source'][:8]}... → {tx['target'][:8]}...) "
                    f"amount={tx['amount']:.2f} tenant={tenant_id}"
                )
            except Exception as e:
                print(f"[Worker] ❌ Neo4j write failed for tx {tx.get('tx_id')}: {e}")
                continue

            # 2. GNN Inference (if engine is available)
            if gnn_engine:
                try:
                    subgraph = neo4j_db.get_neighborhood(tx["source"], tenant_id, hops=2)
                    if subgraph and len(subgraph["nodes"]) > 1:
                        fraud_prob = gnn_engine.predict(subgraph, tx["source"])
                        if fraud_prob > FRAUD_THRESHOLD:
                            neo4j_db.mark_fraud(tx["source"], tenant_id, fraud_prob)
                            print(
                                f"[Worker] 🚨 FRAUD DETECTED: user {tx['source'][:8]}... "
                                f"(score={fraud_prob:.3f}, threshold={FRAUD_THRESHOLD})"
                            )
                    else:
                        pass  # Not enough neighborhood data yet for inference
                except Exception as e:
                    print(f"[Worker] ⚠️  GNN inference error: {e}")

    except asyncio.CancelledError:
        print("[Worker] Consumer cancelled.")
    finally:
        await consumer.stop()
        neo4j_db.close()
        print("[Worker] 🛑 Shut down cleanly.")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()

    # Register signal handlers for graceful shutdown
    if sys.platform != "win32":
        loop.add_signal_handler(signal.SIGTERM, _handle_signal)
        loop.add_signal_handler(signal.SIGINT, _handle_signal)

    try:
        loop.run_until_complete(consume())
    except KeyboardInterrupt:
        print("\n[Worker] Interrupted.")
    finally:
        loop.close()
