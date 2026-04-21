"""
Shared fixtures for GraphGuard API tests.

Provides a FastAPI TestClient with mocked Kafka and Neo4j dependencies,
plus an in-memory SQLite database for API key management.
"""

import os
import sys
import sqlite3
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

# ------------------------------------------------------------------
# Environment setup — must happen BEFORE importing any app modules
# ------------------------------------------------------------------
# Use a temporary SQLite DB so tests don't touch production data
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["SQLITE_DB_PATH"] = _tmp_db.name
_tmp_db.close()

# Prevent Neo4jClient from connecting to a real database on import
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USERNAME", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "test")


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

# Valid test API key
VALID_API_KEY = "sk_test_key_001"
VALID_TENANT_ID = "test_tenant"
VALID_TENANT_NAME = "Test Fintech Corp"

# Second tenant for isolation tests
TENANT_B_API_KEY = "sk_test_key_002"
TENANT_B_ID = "tenant_b"
TENANT_B_NAME = "Beta Finance"


def _init_test_db():
    """Create the api_keys table and seed test keys in the temp SQLite DB."""
    conn = sqlite3.connect(os.environ["SQLITE_DB_PATH"])
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key TEXT UNIQUE NOT NULL,
            tenant_id TEXT NOT NULL,
            name TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Seed two test tenants
    conn.execute(
        "INSERT OR IGNORE INTO api_keys (api_key, tenant_id, name) VALUES (?, ?, ?)",
        (VALID_API_KEY, VALID_TENANT_ID, VALID_TENANT_NAME),
    )
    conn.execute(
        "INSERT OR IGNORE INTO api_keys (api_key, tenant_id, name) VALUES (?, ?, ?)",
        (TENANT_B_API_KEY, TENANT_B_ID, TENANT_B_NAME),
    )
    # Insert an inactive key for testing
    conn.execute(
        "INSERT OR IGNORE INTO api_keys (api_key, tenant_id, name, is_active) VALUES (?, ?, ?, ?)",
        ("sk_disabled_key", "disabled_tenant", "Disabled Corp", 0),
    )
    conn.commit()
    conn.close()


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """One-time test database setup."""
    _init_test_db()
    yield
    # Cleanup temp DB file
    try:
        os.unlink(os.environ["SQLITE_DB_PATH"])
    except OSError:
        pass


@pytest.fixture()
def mock_kafka_producer():
    """Create a mock Kafka producer with async methods."""
    producer = AsyncMock()
    producer.send_and_wait = AsyncMock(return_value=None)
    producer.start = AsyncMock()
    producer.stop = AsyncMock()
    return producer


@pytest.fixture()
def mock_neo4j_client():
    """Create a mock Neo4j client."""
    client = MagicMock()
    client.get_fraudulent_users = MagicMock(return_value=[])
    client.insert_transaction_multitenant = MagicMock()
    client.get_neighborhood = MagicMock(return_value={"nodes": [], "edges": []})
    client.mark_fraud = MagicMock()
    client.get_dashboard_stats = MagicMock(return_value={
        "total_nodes": 0, "total_edges": 0, "fraud_detected_24h": 0,
        "fraud_rate_percentage": 0.0, "last_batch_run": None
    })
    client.get_graph_data = MagicMock(return_value={"nodes": [], "edges": []})
    client.insert_users = MagicMock()
    client.insert_transactions = MagicMock()
    client.close = MagicMock()
    return client


@pytest.fixture()
def client(mock_kafka_producer, mock_neo4j_client):
    """
    Create a FastAPI TestClient with mocked dependencies.

    Overrides the real Kafka producer and Neo4j client so tests run
    without any external infrastructure.
    """
    # We need to patch dependencies BEFORE importing the app
    import api.dependencies as deps
    deps.kafka_producer = mock_kafka_producer
    deps.neo4j_client = mock_neo4j_client

    # Import app after patching
    from api.main import app

    # Override dependency functions to return our mocks
    from api.dependencies import get_kafka_producer, get_neo4j_client
    app.dependency_overrides[get_kafka_producer] = lambda: mock_kafka_producer
    app.dependency_overrides[get_neo4j_client] = lambda: mock_neo4j_client

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client

    # Clean up overrides
    app.dependency_overrides.clear()


@pytest.fixture()
def valid_tx_payload():
    """A valid transaction payload for testing."""
    return {
        "tx_id": "tx_test_001",
        "source": "alice",
        "target": "bob",
        "amount": 250.50,
        "timestamp": 1713400000,
    }


@pytest.fixture()
def auth_headers():
    """Headers with a valid API key."""
    return {"X-API-Key": VALID_API_KEY}


@pytest.fixture()
def tenant_b_headers():
    """Headers with tenant B's API key."""
    return {"X-API-Key": TENANT_B_API_KEY}
