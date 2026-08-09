"""
backend/database.py — Neo4j Connection Layer
Role: Backend Architect (Member 3)

Responsibilities:
- Provide a singleton async Neo4j driver
- Expose helper for running Cypher queries
- Manage connection pooling for FastAPI lifespan
"""

import logging
import os

from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession

load_dotenv()

logger = logging.getLogger("Third Eye.database")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_AUTH_RAW = os.getenv("NEO4J_AUTH", "neo4j/password")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "Third Eye")

_username, _password = NEO4J_AUTH_RAW.split("/", 1)
NEO4J_AUTH = (_username, _password)

# Singleton driver reference — initialized once in FastAPI lifespan
_driver: AsyncDriver | None = None


def get_driver() -> AsyncDriver:
    """
    Return (or initialize) the global Neo4j async driver.
    Called once during FastAPI startup via lifespan context manager.
    """
    global _driver
    if _driver is None:
        logger.info("Initializing Neo4j async driver → %s", NEO4J_URI)
        _driver = AsyncGraphDatabase.driver(
            NEO4J_URI,
            auth=NEO4J_AUTH,
            max_connection_pool_size=50,
            connection_timeout=30.0,
            max_connection_lifetime=60.0,  # Proactively recycle connections every minute
            connection_acquisition_timeout=30.0,
            keep_alive=True,
        )
    return _driver


async def get_session() -> AsyncSession:
    """
    Dependency-injectable Neo4j session factory.
    Usage:
        async with await get_session() as session:
            result = await session.run("MATCH (n) RETURN n LIMIT 10")
    """
    driver = get_driver()
    return driver.session(database=NEO4J_DATABASE)


async def run_query(cypher: str, parameters: dict | None = None) -> list[dict]:
    """
    Execute a Cypher query and return results as a list of plain dicts.
    Convenience wrapper for single-use queries.
    """
    async with await get_session() as session:
        result = await session.run(cypher, parameters or {})
        records = await result.data()
        logger.debug("Cypher query returned %d records", len(records))
        return records


async def verify_connectivity() -> bool:
    """
    Ping the Neo4j instance. Returns True if reachable.
    Called during health checks.
    """
    try:
        driver = get_driver()
        await driver.verify_connectivity()
        logger.info("✅ Neo4j connectivity verified")
        return True
    except Exception as exc:
        logger.error("❌ Neo4j connectivity failed: %s", exc)
        return False


# ── Graph Schema / Constraints ───────────────────────────────
SCHEMA_CYPHER = [
    # Unique constraint on wallet address (idempotent)
    "CREATE CONSTRAINT wallet_address_unique IF NOT EXISTS "
    "FOR (w:Wallet) REQUIRE w.address IS UNIQUE",

    # Index for fast risk score queries
    "CREATE INDEX wallet_risk_score IF NOT EXISTS "
    "FOR (w:Wallet) ON (w.risk_score)",

    # Index for flagged status
    "CREATE INDEX wallet_flagged IF NOT EXISTS "
    "FOR (w:Wallet) ON (w.flagged)",
]


async def apply_schema():
    """
    Idempotently apply Neo4j schema constraints and indexes.
    Call once during application bootstrap or seeding.
    """
    async with await get_session() as session:
        for stmt in SCHEMA_CYPHER:
            await session.run(stmt)
            logger.info("Applied schema: %s", stmt[:60])
    logger.info("✅ Neo4j schema applied successfully")
