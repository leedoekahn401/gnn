from fastapi import APIRouter, Depends, Query
from api.dependencies import get_neo4j_client
from api.security import verify_api_key
from api.schemas import GraphData

router = APIRouter(prefix="/api/v1/graph", tags=["Graph Explorer"])

@router.get("/explore", response_model=GraphData)
def explore_graph(
    min_score: float = Query(0.0, ge=0.0, le=1.0, description="Minimum fraud score to include node"),
    limit: int = Query(100, ge=1, le=1000, description="Max nodes to return"),
    client_info: dict = Depends(verify_api_key),
):
    """Fetch graph nodes and edges for Sigma.js visualization."""
    neo4j_db = get_neo4j_client()
    graph_data = neo4j_db.get_graph_data(
        tenant_id=client_info["tenant_id"],
        min_score=min_score,
        limit=limit
    )
    return graph_data
