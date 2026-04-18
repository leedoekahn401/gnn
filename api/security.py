import hashlib
import sqlite3
import os
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "data/graphguard.db")


def _get_db_connection() -> sqlite3.Connection:
    """Get a connection to the SQLite database."""
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def verify_api_key(api_key: str = Security(api_key_header)) -> dict:
    """
    Validate the API key against the SQLite database.
    Returns client info dict with 'tenant_id' and 'name'.
    """
    conn = _get_db_connection()
    try:
        cursor = conn.execute(
            "SELECT tenant_id, name FROM api_keys WHERE api_key = ? AND is_active = 1",
            (api_key,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Invalid or inactive API Key")
        return {"tenant_id": row["tenant_id"], "name": row["name"]}
    finally:
        conn.close()


def hash_node_id(tenant_id: str, raw_id: str) -> str:
    """Hash user ID to protect PII. Uses tenant_id as salt for isolation."""
    payload = f"{tenant_id}::graphguard::{raw_id}"
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()
