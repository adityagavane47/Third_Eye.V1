"""
scripts/train_ml.py — Third Eye ML Training Script

Fetches all 5,000 wallet nodes + their tx edges from Neo4j Aura,
extracts feature vectors, and fits the IsolationForest model.
Saves the trained model to backend/core/weights/isolation_forest.pkl.

Usage:
    cd d:/NExus/Nexus-Hackathon/backend
    python scripts/train_ml.py
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Make sure backend/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

from core.ml_engine import MLEngine, FEATURE_NAMES, WEIGHTS_PATH
from database import get_driver

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("train_ml")


async def train_from_galaxy():
    driver = get_driver()
    engine = MLEngine()

    logger.info("Connecting to Neo4j and fetching wallet graph...")

    async with driver.session() as session:
        # Fetch all wallets with their outgoing transactions in one query
        result = await session.run(
            """
            MATCH (w:Wallet)
            OPTIONAL MATCH (w)-[r:SENT_TO]->(t:Wallet)
            RETURN
                w.address    AS addr,
                w.label      AS label,
                w.risk_score AS stored_risk,
                collect({
                    to:        t.address,
                    value_eth: r.value_eth,
                    gas_used:  coalesce(r.gas_used, 21000)
                }) AS txs
            """
        )

        training_vectors: list[list[float]] = []
        labels: list[str] = []
        skipped = 0

        async for record in result:
            addr  = record["addr"]
            txs   = [tx for tx in record["txs"] if tx.get("to")]  # filter null edges

            features = engine.extract_features(txs)
            vector   = [features[name] for name in FEATURE_NAMES]

            # Sanity check: skip rows with all-zero vectors (empty wallets)
            if any(v > 0 for v in vector):
                training_vectors.append(vector)
                labels.append(record["label"] or "unknown")
            else:
                skipped += 1

    await driver.close()

    logger.info(
        "Feature extraction complete: %d training samples, %d skipped (empty wallets)",
        len(training_vectors), skipped,
    )

    if len(training_vectors) < 10:
        logger.error("Not enough samples to train (need at least 10). Exiting.")
        return

    # Train the Isolation Forest
    engine._model.train(training_vectors)

    # Save weights
    engine._model.save_weights(WEIGHTS_PATH)
    logger.info("Training complete. Model saved to: %s", WEIGHTS_PATH)

    # Quick validation: score a few samples and print
    test_scores = engine._model.score_samples(training_vectors[:5])
    logger.info("Sample scores (first 5 wallets): %s", [round(s, 3) for s in test_scores])

    # Count how many are flagged as anomalous (score > 0.5)
    all_scores = engine._model.score_samples(training_vectors)
    anomalies_count = sum(1 for s in all_scores if s > 0.5)
    logger.info(
        "Anomaly distribution: %d/%d wallets score above 0.5 (%.1f%%)",
        anomalies_count, len(all_scores), 100 * anomalies_count / len(all_scores),
    )


if __name__ == "__main__":
    asyncio.run(train_from_galaxy())
