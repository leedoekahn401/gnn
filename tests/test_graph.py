from tests.conftest import VALID_TENANT_ID

class TestGraphAPI:
    """GET /api/v1/graph/explore"""

    def test_explore_graph_success(self, client, auth_headers, mock_neo4j_client):
        mock_data = {
            "nodes": [{"key": "u1", "attributes": {"label": "L1", "x": 0, "y": 0, "size": 1, "fraud_score": 0.1, "balance": 100, "is_fraud": False}}],
            "edges": []
        }
        mock_neo4j_client.get_graph_data.return_value = mock_data

        response = client.get("/api/v1/graph/explore?min_score=0.3&limit=50", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["nodes"]) == 1
        mock_neo4j_client.get_graph_data.assert_called_once_with(
            tenant_id=VALID_TENANT_ID,
            min_score=0.3,
            limit=50
        )

    def test_explore_graph_requires_auth(self, client):
        response = client.get("/api/v1/graph/explore")
        assert response.status_code == 401
