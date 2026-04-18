"""
Tests for the Health Check endpoint.
"""


class TestHealthCheck:
    """GET /health"""

    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "graphguard-api"

    def test_health_no_auth_required(self, client):
        """Health endpoint should work without an API key."""
        response = client.get("/health")
        assert response.status_code == 200
