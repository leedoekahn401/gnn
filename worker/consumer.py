"""
GraphGuard Worker Service — Kafka Consumer + Neo4j Writer + Batch GNN Scoring.

Architecture:
    - WRITE PATH:  Kafka consumer ingests transactions and writes them to Neo4j.
                   No inference happens inline — fast and lightweight.
    - SCORING PATH: A periodic batch scheduler queries Neo4j for unscored users,
                    runs GNN inference on their neighborhoods, and flags fraud.

This decoupled design avoids the expensive per-transaction graph scan, replacing
it with a configurable batch interval that amortizes the cost across many users.

Usage:
    python -m worker.consumer

Environment Variables:
    KAFKA_BOOTSTRAP_SERVERS   - Kafka broker address (default: localhost:29092)
    NEO4J_URI                 - Neo4j bolt URI
    NEO4J_USERNAME            - Neo4j username
    NEO4J_PASSWORD            - Neo4j password
    GNN_MODEL_VERSION         - Model checkpoint version to load (default: v1)
    GNN_CHECKPOINT_DIR        - Directory containing model checkpoints (default: gnn/checkpoints)
    FRAUD_THRESHOLD           - Probability threshold to flag fraud (default: 0.7)
    BATCH_INTERVAL_SECONDS    - Seconds between batch scoring runs (default: 60)
    BATCH_SIZE                - Max users to score per batch cycle (default: 100)
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
BATCH_INTERVAL_SECONDS = int(os.getenv("BATCH_INTERVAL_SECONDS", "60"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "100"))

# Graceful shutdown flag
shutdown_event = asyncio.Event()


def _handle_signal():
    print("\n[Worker] Shutdown signal received. Finishing current work...")
    shutdown_event.set()


# ---------------------------------------------------------------------------
#  WRITE PATH — Kafka consumer → Neo4j (no inference)
# ---------------------------------------------------------------------------

async def consume(neo4j_db: Neo4jClient):
    """Kafka consumer loop. Writes transactions to Neo4j only."""
    consumer = AIOKafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        group_id=KAFKA_GROUP,
        auto_offset_reset="earliest",
    )

    await consumer.start()
    print(f"[Consumer] 🎧 Listening on topic '{KAFKA_TOPIC}' (group: {KAFKA_GROUP})...")

    try:
        async for msg in consumer:
            if shutdown_event.is_set():
                break

            data = msg.value
            tenant_id = data.get("tenant_id")
            tx = data.get("transaction")

            if not tenant_id or not tx:
                print(f"[Consumer] ⚠️  Malformed message, skipping: {data}")
                continue

            # Write transaction to Neo4j (multi-tenant)
            try:
                neo4j_db.insert_transaction_multitenant(tx, tenant_id)
                print(
                    f"[Consumer] 📝 Saved tx {tx['tx_id'][:8]}... "
                    f"({tx['source'][:8]}... → {tx['target'][:8]}...) "
                    f"amount={tx['amount']:.2f} tenant={tenant_id}"
                )
            except Exception as e:
                print(f"[Consumer] ❌ Neo4j write failed for tx {tx.get('tx_id')}: {e}")
                continue

    except asyncio.CancelledError:
        print("[Consumer] Cancelled.")
    finally:
        await consumer.stop()
        print("[Consumer] 🛑 Stopped.")


# ---------------------------------------------------------------------------
#  SCORING PATH — Periodic batch GNN inference
# ---------------------------------------------------------------------------

async def batch_scoring_loop(neo4j_db: Neo4jClient):
    """Periodically score unscored users using batch GNN inference."""

    # Load GNN inference engine
    checkpoint_path = os.path.join(GNN_CHECKPOINT_DIR, f"fraud_gnn_model_{GNN_MODEL_VERSION}.pth")
    gnn_engine = None
    if os.path.exists(checkpoint_path):
        gnn_engine = FraudInferenceEngine(checkpoint_path)
        print(f"[Scorer] ✅ GNN model loaded: version '{GNN_MODEL_VERSION}' from {checkpoint_path}")
    else:
        print(f"[Scorer] ⚠️  GNN checkpoint not found at {checkpoint_path}. Batch scoring disabled.")
        return

    print(
        f"[Scorer] ⏰ Batch scoring started — interval={BATCH_INTERVAL_SECONDS}s, "
        f"batch_size={BATCH_SIZE}, threshold={FRAUD_THRESHOLD}"
    )

    while not shutdown_event.is_set():
        try:
            # Fetch users needing (re-)scoring: never scored OR new txs since last score
            unscored_users = neo4j_db.get_unscored_users(limit=BATCH_SIZE)

            if not unscored_users:
                print("[Scorer] 💤 No unscored users. Sleeping...")
            else:
                scored_count = 0
                fraud_count = 0

                for user in unscored_users:
                    if shutdown_event.is_set():
                        break

                    user_id = user["user_id"]
                    tenant_id = user["tenant_id"]

                    try:
                        subgraph = neo4j_db.get_neighborhood(user_id, tenant_id, hops=2)
                        if not subgraph or len(subgraph["nodes"]) <= 1:
                            continue  # Not enough neighborhood data

                        fraud_prob = gnn_engine.predict(subgraph, user_id)
                        scored_count += 1

                        if fraud_prob > FRAUD_THRESHOLD:
                            neo4j_db.mark_fraud(user_id, tenant_id, fraud_prob)
                            fraud_count += 1
                            print(
                                f"[Scorer] 🚨 FRAUD: user {user_id[:8]}... "
                                f"(score={fraud_prob:.3f}, tenant={tenant_id})"
                            )
                        else:
                            neo4j_db.mark_scored(user_id, tenant_id, fraud_prob)
                    except Exception as e:
                        print(f"[Scorer] ⚠️  Inference error for {user_id[:8]}...: {e}")

                print(
                    f"[Scorer] ✅ Batch complete — scored={scored_count}, "
                    f"fraud_flagged={fraud_count}, batch_size={len(unscored_users)}"
                )

        except Exception as e:
            print(f"[Scorer] ❌ Batch scoring error: {e}")

        # Sleep for the batch interval, but wake up early on shutdown
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=BATCH_INTERVAL_SECONDS)
            break  # shutdown_event was set
        except asyncio.TimeoutError:
            pass  # Interval elapsed, run next batch


# ---------------------------------------------------------------------------
#  MAIN — Run both paths concurrently
# ---------------------------------------------------------------------------

async def main():
    """Run the write path and scoring path concurrently."""
    neo4j_db = Neo4jClient()

    try:
        await asyncio.gather(
            consume(neo4j_db),
            batch_scoring_loop(neo4j_db),
        )
    finally:
        neo4j_db.close()
        print("[Worker] 🛑 Shut down cleanly.")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()

    # Register signal handlers for graceful shutdown
    if sys.platform != "win32":
        loop.add_signal_handler(signal.SIGTERM, _handle_signal)
        loop.add_signal_handler(signal.SIGINT, _handle_signal)

    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n[Worker] Interrupted.")
    finally:
        loop.close()
