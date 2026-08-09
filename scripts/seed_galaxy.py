#!/usr/bin/env python3
"""
scripts/seed_galaxy.py — Third Eye Neo4j Seeder
Generates synthetic Web3 wallet nodes and relationships.
"""

import argparse
import asyncio
import logging
import os
import random
import sys
import time
from collections import Counter
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("seed_galaxy")




TOTAL_NODES       = 5_000
BATCH_SIZE        = 250        # Records per Neo4j UNWIND batch
ATTACKER_RATIO    = 0.0        # 0% are attackers initially (starts in peace state)
WHALE_RATIO       = 0.05       # 5% are whales (high balance, low risk)
BOT_RATIO         = 0.08       # 8% are bots
EXCHANGE_RATIO    = 0.10       # 10% are exchanges

# Relationship density bounds per node type
DENSITY = {
    "attacker":  (8, 15),
    "bot":       (5, 10),
    "whale":     (3, 6),
    "exchange":  (4, 8),
    "defi_user": (1, 4),
    "unknown":   (1, 3),
}

HEX_CHARS = "0123456789abcdef"
RISK_THRESHOLD = 0.75   # Wallets above this are auto-flagged




def random_address() -> str:
    """Generate a realistic-looking 42-char Ethereum wallet address."""
    return "0x" + "".join(random.choices(HEX_CHARS, k=40))


def random_tx_hash() -> str:
    """Generate a realistic-looking 66-char Ethereum tx hash."""
    return "0x" + "".join(random.choices(HEX_CHARS, k=64))


def beta_risk_score(is_attacker: bool) -> float:
    if is_attacker:
        return round(min(random.betavariate(8.0, 0.5), 1.0), 4)
    else:
        return round(min(random.betavariate(0.5, 8.0), 1.0), 4)


def assign_label(is_attacker: bool, risk_score: float, rng: float) -> str:
    """
    Assign a human-readable wallet label based on risk profile and a
    random roll to diversify the safe population.
    """
    if is_attacker:
        return "attacker"
    if risk_score > 0.6:
        return "bot"
    if rng < WHALE_RATIO:
        return "whale"
    if rng < WHALE_RATIO + EXCHANGE_RATIO:
        return "exchange"
    if rng < WHALE_RATIO + EXCHANGE_RATIO + BOT_RATIO:
        return "bot"
    return "defi_user"




def generate_wallets(count: int) -> list[dict]:
    """
    Generate synthetic wallet nodes with realistic risk distributions.

    Returns a list of dicts ready to be passed to Neo4j UNWIND.
    """
    logger.info("Generating %d wallet nodes…", count)
    wallets = []
    now = time.time()

    n_attackers = int(count * ATTACKER_RATIO)
    attacker_flags = [True] * n_attackers + [False] * (count - n_attackers)
    random.shuffle(attacker_flags)

    for i, is_attacker in enumerate(attacker_flags):
        risk = beta_risk_score(is_attacker)
        rng = random.random()
        label = assign_label(is_attacker, risk, rng)

        # Whales have high balance, attackers have erratic balance
        if label == "whale":
            balance = round(random.uniform(100.0, 10_000.0), 4)
        elif label == "attacker":
            balance = round(random.uniform(0.001, 50.0), 4)
        elif label == "exchange":
            balance = round(random.uniform(500.0, 50_000.0), 4)
        else:
            balance = round(random.uniform(0.001, 100.0), 4)

        wallets.append({
            "address":    random_address(),
            "risk_score": risk,
            "flagged":    risk > RISK_THRESHOLD,
            "label":      label,
            "tx_count":   random.randint(1, 50_000),
            "balance_eth": balance,
            "first_seen": now - random.randint(86_400, 86_400 * 730),
            "last_seen":  now - random.randint(0, 86_400 * 30),
        })

        if (i + 1) % 500 == 0:
            logger.info("  Generated %d / %d wallets…", i + 1, count)

    return wallets


def generate_relationships(wallets: list[dict]) -> list[dict]:
    logger.info("Generating transaction relationships…")
    relationships = []
    addresses = [w["address"] for w in wallets]
    now = time.time()

    for wallet in wallets:
        label = wallet["label"]
        min_rels, max_rels = DENSITY.get(label, (1, 3))
        n_rels = random.randint(min_rels, max_rels)

        for _ in range(n_rels):
            # Pick a random target (not self)
            target = wallet["address"]
            attempts = 0
            while target == wallet["address"] and attempts < 5:
                target = random.choice(addresses)
                attempts += 1
            if target == wallet["address"]:
                continue

            relationships.append({
                "from":      wallet["address"],
                "to":        target,
                "tx_hash":   random_tx_hash(),
                "value_eth": round(random.uniform(0.001, 100.0), 6),
                "timestamp": now - random.randint(0, 86_400 * 365),
                "gas_used":  random.randint(21_000, 500_000),
            })

    logger.info("  Generated %d relationships across %d wallets", len(relationships), len(wallets))
    return relationships



# NEO4J SEEDING


async def seed_nodes(driver, wallets: list[dict]) -> None:
    """Batch-insert wallet nodes using UNWIND + MERGE (idempotent)."""
    logger.info("Seeding %d wallet nodes (batch size: %d)…", len(wallets), BATCH_SIZE)
    async with driver.session() as session:
        for start in range(0, len(wallets), BATCH_SIZE):
            batch = wallets[start : start + BATCH_SIZE]
            await session.run(
                """
                UNWIND $wallets AS w
                MERGE (wallet:Wallet {address: w.address})
                SET wallet += {
                    risk_score:  w.risk_score,
                    flagged:     w.flagged,
                    label:       w.label,
                    tx_count:    w.tx_count,
                    balance_eth: w.balance_eth,
                    first_seen:  datetime({epochSeconds: toInteger(w.first_seen)}),
                    last_seen:   datetime({epochSeconds: toInteger(w.last_seen)})
                }
                """,
                wallets=batch,
            )
            done = min(start + BATCH_SIZE, len(wallets))
            logger.info("  Nodes seeded: %d / %d", done, len(wallets))


async def seed_relationships(driver, relationships: list[dict]) -> None:
    """Batch-insert SENT_TO edges using UNWIND + MERGE (idempotent)."""
    logger.info("Seeding %d relationships (batch size: %d)…", len(relationships), BATCH_SIZE)
    async with driver.session() as session:
        for start in range(0, len(relationships), BATCH_SIZE):
            batch = relationships[start : start + BATCH_SIZE]
            await session.run(
                """
                UNWIND $rels AS r
                MATCH (from:Wallet {address: r.from})
                MATCH (to:Wallet   {address: r.to})
                MERGE (from)-[tx:SENT_TO {tx_hash: r.tx_hash}]->(to)
                SET tx += {
                    value_eth: r.value_eth,
                    timestamp: datetime({epochSeconds: toInteger(r.timestamp)}),
                    gas_used:  r.gas_used
                }
                """,
                rels=batch,
            )
            done = min(start + BATCH_SIZE, len(relationships))
            logger.info("  Relationships seeded: %d / %d", done, len(relationships))




def print_summary_report(wallets: list[dict], relationships: list[dict], elapsed: float) -> None:
    """
    Print a detailed summary of the seeded data to the console.
    """
    label_counts = Counter(w["label"] for w in wallets)
    flagged_count = sum(1 for w in wallets if w["flagged"])
    avg_risk = sum(w["risk_score"] for w in wallets) / len(wallets)
    avg_edges = len(relationships) / len(wallets)

    print("\n" + "=" * 60)
    print("  Third Eye -- SEED REPORT")
    print("=" * 60)
    print(f"  Total nodes:          {len(wallets):>8,}")
    print(f"  Total relationships:  {len(relationships):>8,}")
    print(f"  Flagged wallets:      {flagged_count:>8,}  ({flagged_count/len(wallets)*100:.1f}%)")
    print(f"  Avg risk score:       {avg_risk:>8.4f}")
    print(f"  Avg edges per node:   {avg_edges:>8.2f}")
    print(f"  Elapsed time:         {elapsed:>7.1f}s")
    print()
    print("  LABEL DISTRIBUTION")
    print("  " + "-" * 40)
    for label, count in sorted(label_counts.items(), key=lambda x: -x[1]):
        bar = "#" * int(count / len(wallets) * 40)
        print(f"  {label:<14} {count:>5,}  {count/len(wallets)*100:>5.1f}%  {bar}")
    print("=" * 60 + "\n")




async def seed(reset: bool = False, total_nodes: int = TOTAL_NODES) -> None:
    """Main seeding coroutine."""
    from database import apply_schema, get_driver, run_query

    driver = get_driver()
    t0 = time.time()

    # Optional reset
    if reset:
        logger.warning("⚠️  RESET flag set — deleting all existing wallet data…")
        await run_query("MATCH (n:Wallet) DETACH DELETE n")
        logger.info("  Wallet nodes cleared.")

    # Apply schema constraints and indexes (idempotent)
    logger.info("Applying Neo4j schema constraints and indexes…")
    await apply_schema()

    # Generate data
    wallets = generate_wallets(total_nodes)
    relationships = generate_relationships(wallets)

    # Push to Neo4j
    await seed_nodes(driver, wallets)
    await seed_relationships(driver, relationships)

    elapsed = time.time() - t0
    logger.info("✅ Galaxy seeded successfully in %.1fs", elapsed)

    # Print summary report
    print_summary_report(wallets, relationships, elapsed)

    driver.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Third Eye — Neo4j Database Seeder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/seed_galaxy.py                  # Seed 5,000 nodes
  python scripts/seed_galaxy.py --nodes 1000     # Seed 1,000 nodes (quick test)
  python scripts/seed_galaxy.py --reset          # Wipe existing data first
        """,
    )
    parser.add_argument(
        "--nodes",
        type=int,
        default=TOTAL_NODES,
        help=f"Number of wallet nodes to generate (default: {TOTAL_NODES})",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete all existing :Wallet nodes before seeding",
    )
    args = parser.parse_args()

    asyncio.run(seed(reset=args.reset, total_nodes=args.nodes))
