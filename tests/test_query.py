"""
Tests for the Fraud Alerts Query endpoint.

GET /api/v1/alerts/fraudulent-users
"""

from tests.conftest import VALID_TENANT_ID, VALID_TENANT_NAME, TENANT_B_ID, TENANT_B_NAME


class TestQueryFraudulentUsers:
    """GET /api/v1/alerts/fraudulent-users"""

    def test_query_success_empty(self, client, auth_headers, mock_neo4j_client):
        """When no fraud users exist, should return empty list."""
        mock_neo4j_client.get_fraudulent_users.return_value = []

        response = client.get(
            "/api/v1/alerts/fraudulent-users",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["tenant"] == VALID_TENANT_NAME
        assert data["fraud_users"] == []

    def test_query_returns_fraud_users(self, client, auth_headers, mock_neo4j_client):
        """Should return fraud users from Neo4j."""
        mock_neo4j_client.get_fraudulent_users.return_value = [
            {"hashed_user_id": "abc123def456", "balance": 5000.0, "fraud_score": 0.95},
            {"hashed_user_id": "789ghi012jkl", "balance": 200.0, "fraud_score": 0.82},
        ]

        response = client.get(
            "/api/v1/alerts/fraudulent-users",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["fraud_users"]) == 2
        assert data["fraud_users"][0]["hashed_user_id"] == "abc123def456"
        assert data["fraud_users"][0]["fraud_score"] == 0.95
        assert data["fraud_users"][1]["balance"] == 200.0

    def test_query_passes_tenant_id(self, client, auth_headers, mock_neo4j_client):
        """Should query Neo4j with the correct tenant_id."""
        client.get(
            "/api/v1/alerts/fraudulent-users",
            headers=auth_headers,
        )
        mock_neo4j_client.get_fraudulent_users.assert_called_once_with(
            tenant_id=VALID_TENANT_ID,
            limit=10,  # default
        )

    def test_query_custom_limit(self, client, auth_headers, mock_neo4j_client):
        """Should pass the limit parameter to Neo4j."""
        client.get(
            "/api/v1/alerts/fraudulent-users?limit=5",
            headers=auth_headers,
        )
        mock_neo4j_client.get_fraudulent_users.assert_called_once_with(
            tenant_id=VALID_TENANT_ID,
            limit=5,
        )

    def test_query_requires_auth(self, client):
        """Should fail without API key."""
        response = client.get("/api/v1/alerts/fraudulent-users")
        assert response.status_code == 401

    def test_query_invalid_key(self, client):
        response = client.get(
            "/api/v1/alerts/fraudulent-users",
            headers={"X-API-Key": "sk_wrong"},
        )
        assert response.status_code == 401


class TestQueryValidation:
    """Query parameter validation."""

    def test_limit_zero_rejected(self, client, auth_headers):
        """Limit must be >= 1."""
        response = client.get(
            "/api/v1/alerts/fraudulent-users?limit=0",
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_limit_negative_rejected(self, client, auth_headers):
        response = client.get(
            "/api/v1/alerts/fraudulent-users?limit=-5",
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_limit_exceeds_max_rejected(self, client, auth_headers):
        """Limit must be <= 100."""
        response = client.get(
            "/api/v1/alerts/fraudulent-users?limit=200",
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_limit_max_boundary(self, client, auth_headers, mock_neo4j_client):
        """Limit of 100 should be accepted."""
        mock_neo4j_client.get_fraudulent_users.return_value = []
        response = client.get(
            "/api/v1/alerts/fraudulent-users?limit=100",
            headers=auth_headers,
        )
        assert response.status_code == 200


class TestMultiTenantIsolation:
    """Verify that different API keys route to different tenant_ids."""

    def test_tenant_a_sees_own_data(self, client, auth_headers, mock_neo4j_client):
        """Tenant A should query with their own tenant_id."""
        client.get(
            "/api/v1/alerts/fraudulent-users",
            headers=auth_headers,
        )
        mock_neo4j_client.get_fraudulent_users.assert_called_with(
            tenant_id=VALID_TENANT_ID,
            limit=10,
        )

    def test_tenant_b_sees_own_data(self, client, tenant_b_headers, mock_neo4j_client):
        """Tenant B should query with their own tenant_id."""
        client.get(
            "/api/v1/alerts/fraudulent-users",
            headers=tenant_b_headers,
        )
        mock_neo4j_client.get_fraudulent_users.assert_called_with(
            tenant_id=TENANT_B_ID,
            limit=10,
        )

    def test_tenant_name_in_response(self, client, tenant_b_headers, mock_neo4j_client):
        """Response should include the correct tenant name."""
        mock_neo4j_client.get_fraudulent_users.return_value = []
        response = client.get(
            "/api/v1/alerts/fraudulent-users",
            headers=tenant_b_headers,
        )
        assert response.json()["tenant"] == TENANT_B_NAME
