from fastapi import APIRouter, Depends
from api.dependencies import get_neo4j_client
from api.security import verify_api_key
from api.schemas import DashboardStats

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])

@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(
    client_info: dict = Depends(verify_api_key),
):
    """Fetch high-level metrics for the overview dashboard."""
    neo4j_db = get_neo4j_client()
    stats = neo4j_db.get_dashboard_stats(tenant_id=client_info["tenant_id"])
    return stats
