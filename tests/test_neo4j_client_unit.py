from unittest.mock import MagicMock, patch
from db.neo4j_client import Neo4jClient

class TestNeo4jClientUnit:
    @patch("db.neo4j_client.GraphDatabase.driver")
    def test_get_dashboard_stats(self, mock_driver_constructor):
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_record = MagicMock()
        
        mock_driver_constructor.return_value = mock_driver
        mock_driver.session.return_value.__enter__.return_value = mock_session
        mock_session.run.return_value = mock_result
        mock_result.single.return_value = mock_record
        
        # Setup mock record behavior
        mock_record.__getitem__.side_state = lambda key: {
            "total_nodes": 10, "total_edges": 20, "fraud_detected": 2, "fraud_rate": 20.0, "last_run": None
        }[key]
        mock_record.get.side_effect = lambda key, default=None: {
            "total_nodes": 10, "total_edges": 20, "fraud_detected": 2, "fraud_rate": 20.0, "last_run": None
        }.get(key, default)

        # Simplified mocking for record Access
        mock_record.__getitem__ = MagicMock(side_effect=lambda k: {
             "total_nodes": 10, "total_edges": 20, "fraud_detected": 2, "fraud_rate": 20.0, "last_run": None
        }.get(k))

        client = Neo4jClient()
        stats = client.get_dashboard_stats("test_tenant")
        
        assert stats["total_nodes"] == 10
        assert stats["total_edges"] == 20
        mock_session.run.assert_called_once()
        query_arg = mock_session.run.call_args[0][0]
        assert "MATCH (u:User {tenant_id: $tenant_id})" in query_arg

    @patch("db.neo4j_client.GraphDatabase.driver")
    def test_insert_users_with_tenant(self, mock_driver_constructor):
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver_constructor.return_value = mock_driver
        mock_driver.session.return_value.__enter__.return_value = mock_session
        
        client = Neo4jClient()
        users = [{"id": "u1", "is_fraud": False, "balance": 10.0}]
        client.insert_users(users, tenant_id="tenant_x")
        
        mock_session.run.assert_called_once()
        args, kwargs = mock_session.run.call_args
        assert kwargs["tenant_id"] == "tenant_x"
        assert "MERGE (u:User {id: user.id, tenant_id: $tenant_id})" in args[0]
