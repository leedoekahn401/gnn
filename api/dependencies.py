from aiokafka import AIOKafkaProducer
from db.neo4j_client import Neo4jClient

# Global instances managed by the FastAPI lifespan
kafka_producer: AIOKafkaProducer | None = None
neo4j_client: Neo4jClient = Neo4jClient()

KAFKA_TOPIC = "raw_transactions"


def get_kafka_producer() -> AIOKafkaProducer:
    """Dependency to get the Kafka producer instance."""
    return kafka_producer


def get_neo4j_client() -> Neo4jClient:
    """Dependency to get the Neo4j client instance."""
    return neo4j_client
