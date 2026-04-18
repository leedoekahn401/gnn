"""
Tests for API Key authentication and PII hashing.
"""

import hashlib
from tests.conftest import VALID_API_KEY, VALID_TENANT_ID, VALID_TENANT_NAME


class TestAuthentication:
    """API key validation via X-API-Key header."""

    def test_missing_api_key_returns_403(self, client):
        """FastAPI returns 403 when APIKeyHeader is missing (auto_error=True)."""
        response = client.get("/api/v1/alerts/fraudulent-users")
        assert response.status_code == 403

    def test_invalid_api_key_returns_401(self, client):
        """An unknown key should be rejected with 401."""
        response = client.get(
            "/api/v1/alerts/fraudulent-users",
            headers={"X-API-Key": "sk_invalid_garbage"},
        )
        assert response.status_code == 401
        assert "Invalid" in response.json()["detail"]

    def test_disabled_api_key_returns_401(self, client):
        """An inactive key in the DB should be rejected."""
        response = client.get(
            "/api/v1/alerts/fraudulent-users",
            headers={"X-API-Key": "sk_disabled_key"},
        )
        assert response.status_code == 401

    def test_valid_api_key_passes(self, client, auth_headers):
        """A valid key should authenticate successfully."""
        response = client.get(
            "/api/v1/alerts/fraudulent-users",
            headers=auth_headers,
        )
        assert response.status_code == 200


class TestPIIHashing:
    """SHA-256 hashing with tenant salt."""

    def test_hash_is_deterministic(self):
        """Same input should always produce the same hash."""
        from api.security import hash_node_id

        h1 = hash_node_id("tenant_a", "alice")
        h2 = hash_node_id("tenant_a", "alice")
        assert h1 == h2

    def test_hash_differs_across_tenants(self):
        """Different tenants hashing the same user ID should get different hashes."""
        from api.security import hash_node_id

        h_a = hash_node_id("tenant_a", "alice")
        h_b = hash_node_id("tenant_b", "alice")
        assert h_a != h_b

    def test_hash_format_is_sha256(self):
        """Hash should be a 64-char hex string (SHA-256)."""
        from api.security import hash_node_id

        h = hash_node_id("t", "u")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_matches_manual_computation(self):
        """Verify the hash matches a direct SHA-256 computation."""
        from api.security import hash_node_id

        tenant, user = "startup_a", "bob"
        expected = hashlib.sha256(
            f"{tenant}::graphguard::{user}".encode("utf-8")
        ).hexdigest()
        assert hash_node_id(tenant, user) == expected
