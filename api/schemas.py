from pydantic import BaseModel, Field


class TransactionInput(BaseModel):
    """Schema for incoming transaction data from clients."""
    tx_id: str = Field(..., description="Unique Transaction ID")
    source: str = Field(..., description="Sender User ID (Plain text)")
    target: str = Field(..., description="Receiver User ID (Plain text)")
    amount: float = Field(..., gt=0, description="Transaction amount (must be positive)")
    timestamp: int = Field(..., description="Unix timestamp of the transaction")


class TransactionResponse(BaseModel):
    """Response after successfully ingesting a transaction."""
    status: str = "success"
    message: str = "Transaction securely anonymized and queued."


class FraudUserOut(BaseModel):
    """Schema for a single fraudulent user in query results."""
    hashed_user_id: str
    balance: float | None = None
    fraud_score: float | None = None


class FraudUsersResponse(BaseModel):
    """Response for the fraudulent users query."""
    tenant: str
    fraud_users: list[FraudUserOut]


class DashboardStats(BaseModel):
    total_nodes: int
    total_edges: int
    fraud_detected_24h: int
    fraud_rate_percentage: float
    last_batch_run: str | None


class GraphNodeAttributes(BaseModel):
    label: str
    x: float
    y: float
    size: float
    fraud_score: float
    balance: float
    is_fraud: bool


class GraphNode(BaseModel):
    key: str
    attributes: GraphNodeAttributes


class GraphEdgeAttributes(BaseModel):
    size: float
    amount: float


class GraphEdge(BaseModel):
    key: str
    source: str
    target: str
    attributes: GraphEdgeAttributes


class GraphData(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class SimulationRequest(BaseModel):
    normal_agents: int = 50
    fraud_agents: int = 10
    epochs: int = 100


class SimulationJobResponse(BaseModel):
    job_id: str
    status: str


class SimulationMetrics(BaseModel):
    f1_score: float
    precision: float
    recall: float
    auc: float


class SimulationResults(BaseModel):
    status: str
    metrics: SimulationMetrics | None = None


   