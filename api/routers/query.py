from fastapi import APIRouter, Depends, Query

from api.dependencies import get_neo4j_client
from api.security import verify_api_key
from api.schemas import FraudUsersResponse

router = APIRouter(prefix="/api/v1/alerts", tags=["Alerts"])


@router.get("/fraudulent-users", response_model=FraudUsersResponse)
def get_fraudulent_users(
    limit: int = Query(default=10, ge=1, le=100, description="Max users to return"),
    client_info: dict = Depends(verify_api_key),
):
    """
    Query flagged fraudulent users for the authenticated tenant.

    Returns a list of hashed user IDs, balances, and fraud scores —
    filtered by the tenant's data partition.
    """
    neo4j_db = get_neo4j_client()
    results = neo4j_db.get_fraudulent_users(
        tenant_id=client_info["tenant_id"],
        limit=limit,
    )

    return FraudUsersResponse(
        tenant=client_info["name"],
        fraud_users=results,
    )
