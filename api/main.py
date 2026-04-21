import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from aiokafka import AIOKafkaProducer

import api.dependencies as deps
from api.routers import ingest, query, dashboard, graph, sandbox
from api.init_db import init_database, seed_default_key


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle:
    - Startup: Initialize SQLite, start Kafka producer
    - Shutdown: Stop Kafka producer, close Neo4j driver
    """
    # --- Startup ---
    # Initialize SQLite for API key storage
    init_database()
    seed_default_key()

    # Create Neo4j constraints/indexes
    deps.neo4j_client.create_constraints()

    # Start Kafka producer
    deps.kafka_producer = AIOKafkaProducer(
        bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092"),
    )
    await deps.kafka_producer.start()
    print("🚀 GraphGuard API is ready.")

    yield

    # --- Shutdown ---
    await deps.kafka_producer.stop()
    deps.neo4j_client.close()
    print("🛑 GraphGuard API shut down gracefully.")


app = FastAPI(
    title="GraphGuard API",
    description="Multi-tenant Fraud Detection SaaS — Ingest transactions and query fraud alerts.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest.router)
app.include_router(query.router)
app.include_router(dashboard.router)
app.include_router(graph.router)
app.include_router(sandbox.router)


@app.get("/health", tags=["Health"])
def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "service": "graphguard-api"}
