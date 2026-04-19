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


   