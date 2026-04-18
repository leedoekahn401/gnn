"""
SQLite database initialization for API key management.
Run this module directly to create the schema and seed a default API key.

Usage:
    python -m api.init_db
"""

import sqlite3
import os


SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "data/graphguard.db")


def init_database():
    """Create the SQLite database schema if it doesn't exist."""
    os.makedirs(os.path.dirname(SQLITE_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(SQLITE_DB_PATH)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_key TEXT UNIQUE NOT NULL,
                tenant_id TEXT NOT NULL,
                name TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        print(f"✅ Database initialized at: {SQLITE_DB_PATH}")
    finally:
        conn.close()


def seed_default_key():
    """Insert a default API key for development/testing."""
    conn = sqlite3.connect(SQLITE_DB_PATH)
    try:
        # Check if key already exists
        cursor = conn.execute(
            "SELECT COUNT(*) FROM api_keys WHERE api_key = ?",
            ("sk_live_abc123",)
        )
        if cursor.fetchone()[0] == 0:
            conn.execute(
                "INSERT INTO api_keys (api_key, tenant_id, name) VALUES (?, ?, ?)",
                ("sk_live_abc123", "startup_a", "Alpha Fintech")
            )
            conn.commit()
            print("🔑 Default API key seeded: sk_live_abc123 -> tenant 'startup_a'")
        else:
            print("🔑 Default API key already exists, skipping seed.")
    finally:
        conn.close()


if __name__ == "__main__":
    init_database()
    seed_default_key()
