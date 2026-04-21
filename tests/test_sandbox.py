import time

class TestSandboxAPI:
    """POST /api/v1/sandbox/simulate and GET /api/v1/sandbox/results/{job_id}"""

    def test_trigger_simulation_success(self, client, auth_headers):
        payload = {
            "normal_agents": 20,
            "fraud_agents": 5,
            "epochs": 10
        }
        response = client.post("/api/v1/sandbox/simulate", json=payload, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "processing"

    def test_get_results_not_found(self, client, auth_headers):
        response = client.get("/api/v1/sandbox/results/non_existent", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "not_found"

    def test_simulation_workflow(self, client, auth_headers):
        # Trigger
        res = client.post("/api/v1/sandbox/simulate", json={"normal_agents": 10}, headers=auth_headers)
        job_id = res.json()["job_id"]

        # Poll (wait a bit for background task)
        # Note: In real tests we might mock the background task to be synchronous or use a wait loop
        # For this test, since it's an in-memory mock worker, it might be fast.
        
        max_retries = 5
        completed = False
        for _ in range(max_retries):
            res = client.get(f"/api/v1/sandbox/results/{job_id}", headers=auth_headers)
            if res.json()["status"] == "completed":
                completed = True
                break
            time.sleep(1)
        
        assert completed
        assert "metrics" in res.json()
        assert res.json()["metrics"]["f1_score"] > 0
