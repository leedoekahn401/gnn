import json
from fastapi import APIRouter, Depends
from aiokafka import AIOKafkaProducer

from api.schemas import TransactionInput, TransactionResponse
from api.dependencies import get_kafka_producer, KAFKA_TOPIC
from api.security import verify_api_key, hash_node_id

router = APIRouter(prefix="/api/v1/ingest", tags=["Ingestion"])


@router.post("/transaction", response_model=TransactionResponse)
async def ingest_transaction(
    tx: TransactionInput,
    client_info: dict = Depends(verify_api_key),
    producer: AIOKafkaProducer = Depends(get_kafka_producer),
):
    """
    Ingest a new transaction.

    The source and target user IDs are hashed with the tenant's salt
    before being published to Kafka — ensuring zero-knowledge PII protection.
    """
    tenant_id = client_info["tenant_id"]

    # Anonymize data (Zero-Knowledge Pseudonymization)
    anonymized_tx = {
        "tx_id": tx.tx_id,
        "source": hash_node_id(tenant_id, tx.source),
        "target": hash_node_id(tenant_id, tx.target),
        "amount": tx.amount,
        "timestamp": tx.timestamp,
    }

    message = {"tenant_id": tenant_id, "transaction": anonymized_tx}

    await producer.send_and_wait(
        KAFKA_TOPIC,
        json.dumps(message).encode("utf-8"),
    )

    return TransactionResponse()
