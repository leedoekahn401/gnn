"""
Tests for the Transaction Ingestion endpoint.

POST /api/v1/ingest/transaction
"""

import json
from unittest.mock import AsyncMock
from tests.conftest import VALID_API_KEY, VALID_TENANT_ID


class TestIngestTransaction:
    """POST /api/v1/ingest/transaction"""

    def test_ingest_success(self, client, auth_headers, valid_tx_payload, mock_kafka_producer):
        """Valid transaction should be accepted and published to Kafka."""
        response = client.post(
            "/api/v1/ingest/transaction",
            json=valid_tx_payload,
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "anonymized" in data["message"].lower() or "queued" in data["message"].lower()

        # Verify Kafka was called
        mock_kafka_producer.send_and_wait.assert_called_once()

    def test_ingest_kafka_message_structure(self, client, auth_headers, valid_tx_payload, mock_kafka_producer):
        """Verify the Kafka message has the correct structure."""
        client.post(
            "/api/v1/ingest/transaction",
            json=valid_tx_payload,
            headers=auth_headers,
        )

        call_args = mock_kafka_producer.send_and_wait.call_args
        topic = call_args[0][0]
        raw_message = call_args[0][1]
        message = json.loads(raw_message.decode("utf-8"))

        # Check topic
        assert topic == "raw_transactions"

        # Check message structure
        assert "tenant_id" in message
        assert message["tenant_id"] == VALID_TENANT_ID
        assert "transaction" in message

        tx = message["transaction"]
        assert tx["tx_id"] == valid_tx_payload["tx_id"]
        assert tx["amount"] == valid_tx_payload["amount"]
        assert tx["timestamp"] == valid_tx_payload["timestamp"]

    def test_ingest_hashes_source_and_target(self, client, auth_headers, valid_tx_payload, mock_kafka_producer):
        """Source and target should be SHA-256 hashed, not plain text."""
        client.post(
            "/api/v1/ingest/transaction",
            json=valid_tx_payload,
            headers=auth_headers,
        )

        raw_message = mock_kafka_producer.send_and_wait.call_args[0][1]
        message = json.loads(raw_message.decode("utf-8"))
        tx = message["transaction"]

        # Hashed IDs should be 64-char hex, NOT the original plain text
        assert tx["source"] != valid_tx_payload["source"]
        assert tx["target"] != valid_tx_payload["target"]
        assert len(tx["source"]) == 64
        assert len(tx["target"]) == 64

    def test_ingest_requires_auth(self, client, valid_tx_payload):
        """Should fail without API key."""
        response = client.post(
            "/api/v1/ingest/transaction",
            json=valid_tx_payload,
        )
        assert response.status_code == 403

    def test_ingest_invalid_api_key(self, client, valid_tx_payload):
        """Should reject invalid API key."""
        response = client.post(
            "/api/v1/ingest/transaction",
            json=valid_tx_payload,
            headers={"X-API-Key": "sk_fake_key"},
        )
        assert response.status_code == 401


class TestIngestValidation:
    """Request body validation for transaction ingestion."""

    def test_missing_tx_id(self, client, auth_headers):
        response = client.post(
            "/api/v1/ingest/transaction",
            json={"source": "a", "target": "b", "amount": 100, "timestamp": 1000},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_missing_source(self, client, auth_headers):
        response = client.post(
            "/api/v1/ingest/transaction",
            json={"tx_id": "t1", "target": "b", "amount": 100, "timestamp": 1000},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_missing_target(self, client, auth_headers):
        response = client.post(
            "/api/v1/ingest/transaction",
            json={"tx_id": "t1", "source": "a", "amount": 100, "timestamp": 1000},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_missing_amount(self, client, auth_headers):
        response = client.post(
            "/api/v1/ingest/transaction",
            json={"tx_id": "t1", "source": "a", "target": "b", "timestamp": 1000},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_missing_timestamp(self, client, auth_headers):
        response = client.post(
            "/api/v1/ingest/transaction",
            json={"tx_id": "t1", "source": "a", "target": "b", "amount": 100},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_zero_amount_rejected(self, client, auth_headers):
        """Amount must be > 0."""
        response = client.post(
            "/api/v1/ingest/transaction",
            json={"tx_id": "t1", "source": "a", "target": "b", "amount": 0, "timestamp": 1000},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_negative_amount_rejected(self, client, auth_headers):
        response = client.post(
            "/api/v1/ingest/transaction",
            json={"tx_id": "t1", "source": "a", "target": "b", "amount": -50, "timestamp": 1000},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_empty_body_rejected(self, client, auth_headers):
        response = client.post(
            "/api/v1/ingest/transaction",
            json={},
            headers=auth_headers,
        )
        assert response.status_code == 422
