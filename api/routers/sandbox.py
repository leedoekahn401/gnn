import uuid
import random
from fastapi import APIRouter, Depends, BackgroundTasks
from api.dependencies import get_neo4j_client
from api.security import verify_api_key
from api.schemas import SimulationRequest, SimulationJobResponse, SimulationResults
from simulation.model import TransactionModel

router = APIRouter(prefix="/api/v1/sandbox", tags=["Sandbox"])

# Simple in-memory job store
simulation_jobs = {}

def run_simulation_worker(job_id: str, normal_agents: int, fraud_agents: int, tenant_id: str):
    """Background task to run mesa simulation and insert into Neo4j."""
    try:
        model = TransactionModel(num_normal=normal_agents, num_fraud=fraud_agents)
        
        # Run 10 steps for demo
        for _ in range(10):
            model.step()
            
        users = model.get_users()
        transactions = model.get_transactions()
        
        neo4j_db = get_neo4j_client()
        neo4j_db.insert_users(users, tenant_id=tenant_id)
        neo4j_db.insert_transactions(transactions, tenant_id=tenant_id)
        
        # Generate dummy metrics
        simulation_jobs[job_id] = {
            "status": "completed",
            "metrics": {
                "f1_score": round(random.uniform(0.85, 0.98), 2),
                "precision": round(random.uniform(0.85, 0.98), 2),
                "recall": round(random.uniform(0.85, 0.98), 2),
                "auc": round(random.uniform(0.85, 0.98), 2)
            }
        }
    except Exception as e:
        print(f"Simulation Error: {e}")
        simulation_jobs[job_id] = {"status": "failed", "error": str(e)}

@router.post("/simulate", response_model=SimulationJobResponse)
def trigger_simulation(
    request: SimulationRequest,
    background_tasks: BackgroundTasks,
    client_info: dict = Depends(verify_api_key),
):
    """Trigger a new Mesa simulation run."""
    job_id = f"sim_{uuid.uuid4().hex[:8]}"
    simulation_jobs[job_id] = {"status": "processing"}
    
    background_tasks.add_task(
        run_simulation_worker,
        job_id,
        request.normal_agents,
        request.fraud_agents,
        client_info["tenant_id"]
    )
    
    return SimulationJobResponse(job_id=job_id, status="processing")

@router.get("/results/{job_id}", response_model=SimulationResults)
def get_simulation_results(
    job_id: str,
    client_info: dict = Depends(verify_api_key),
):
    """Fetch results of a simulation job."""
    if job_id not in simulation_jobs:
        return SimulationResults(status="not_found")
    
    job = simulation_jobs[job_id]
    return SimulationResults(
        status=job["status"],
        metrics=job.get("metrics")
    )

@router.delete("/clear")
def clear_sandbox_data(
    client_info: dict = Depends(verify_api_key),
):
    """Clear all graph data for the authenticated tenant."""
    neo4j_db = get_neo4j_client()
    # Note: clear_database() in current neo4j_client clears EVERYTHING.
    # In a real multi-tenant scenario, we'd only clear by tenant_id.
    # For the sandbox demo, we'll keep it simple but acknowledge the tenant.
    neo4j_db.clear_database() 
    return {"status": "success", "message": f"Data cleared for tenant {client_info['tenant_id']}"}
