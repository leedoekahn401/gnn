from tests.conftest import VALID_TENANT_ID

class TestDashboardAPI:
    """GET /api/v1/dashboard/stats"""

    def test_get_stats_success(self, client, auth_headers, mock_neo4j_client):
        mock_stats = {
            "total_nodes": 100,
            "total_edges": 500,
            "fraud_detected_24h": 5,
            "fraud_rate_percentage": 5.0,
            "last_batch_run": "2024-05-20T10:30:00Z"
        }
        mock_neo4j_client.get_dashboard_stats.return_value = mock_stats

        response = client.get("/api/v1/dashboard/stats", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_nodes"] == 100
        assert data["fraud_rate_percentage"] == 5.0
        mock_neo4j_client.get_dashboard_stats.assert_called_once_with(tenant_id=VALID_TENANT_ID)

    def test_get_stats_requires_auth(self, client):
        response = client.get("/api/v1/dashboard/stats")
        assert response.status_code == 401
