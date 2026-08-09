#!/usr/bin/env python3
"""
scripts/seed_real.py — Third Eye Real Blockchain Seeder

Replaces synthetic mock data with real Ethereum on-chain wallet data
sourced from the Etherscan API.

Strategy:
  1. Start from a curated list of known real-world attacker/whale wallets
  2. BFS-crawl their counterparties (depth 1 or 2)
  3. For each wallet: fetch txs, run ML scoring, write to Neo4j

Usage:
  python scripts/seed_real.py                     # Default: seed wallets list, depth=1
  python scripts/seed_real.py --depth 2           # BFS depth 2 (much more data)
  python scripts/seed_real.py --max-wallets 100   # Cap at 100 wallets
  python scripts/seed_real.py --reset             # Wipe existing data first
  python scripts/seed_real.py --extra 0xABC...    # Add a custom seed wallet
"""

import argparse
import asyncio
import logging
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
logger = logging.getLogger("seed_real")


# ── Curated Seed Wallets ──────────────────────────────────────────────────────
# Real, verified addresses from public blockchain data and security reports.
# These represent the full spectrum: hackers, whales, mixers, DeFi users.

SEED_WALLETS = [
    # ── Major Exploiters / Hackers ──────────────────────────────────────────
    {
        "address": "0x098B716B8Aaf21512996dC57EB0615e2383E2f96",
        "hint":    "Ronin Bridge Hacker (Lazarus Group) — $625M exploit",
        "label":   "attacker",
    },
    {
        "address": "0x1db3439a222C519ab44bb1144fC28167b4Fa6EE6",
        "hint":    "Euler Finance Hacker — $200M flash loan exploit",
        "label":   "attacker",
    },
    {
        "address": "0xA090e606E30bD747d4E6245a1517EbE430F0057e",
        "hint":    "Nomad Bridge Hacker — $190M exploit",
        "label":   "attacker",
    },
    {
        "address": "0xB3764761E297D6f121e79C32A65829Cd1dDb4D32",
        "hint":    "Tornado Cash relayer — known mixing node",
        "label":   "attacker",
    },

    # ── Known Whales / Institutions ─────────────────────────────────────────
    {
        "address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
        "hint":    "Vitalik Buterin — Ethereum co-founder",
        "label":   "whale",
    },
    {
        "address": "0x47ac0Fb4F2D84898e4D9E7b4DaB3C24507a6D503",
        "hint":    "Binance Hot Wallet — major exchange",
        "label":   "exchange",
    },
    {
        "address": "0xBE0eB53F46cd790Cd13851d5EFf43D12404d33E8",
        "hint":    "Binance Cold Wallet — large ETH holder",
        "label":   "exchange",
    },
    {
        "address": "0x3f5CE5FBFe3E9af3971dD833D26bA9b5C936f0bE",
        "hint":    "Binance Exchange Wallet",
        "label":   "exchange",
    },

    # ── DeFi Power Users ────────────────────────────────────────────────────
    {
        "address": "0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B",
        "hint":    "Vitalik donor wallet — active DeFi participant",
        "label":   "defi_user",
    },
    {
        "address": "0x220866B1A2219f40e72f5c628B65D54268cA3A9D",
        "hint":    "Active DeFi user — multi-protocol interactions",
        "label":   "defi_user",
    },

    # ── MEV Bots ────────────────────────────────────────────────────────────
    {
        "address": "0x00000000003b3cc22aF3aE1EAc0440BcEe416B40",
        "hint":    "MEV Bot — high frequency frontrunning bot",
        "label":   "bot",
    },
    {
        "address": "0x6b75d8AF000000e20B7a7DDf000Ba900b4009A80",
        "hint":    "Sandwich attack bot",
        "label":   "bot",
    },
]

RISK_THRESHOLD = 0.75


# ── Risk Score Estimation ─────────────────────────────────────────────────────

async def estimate_risk(address: str, tx_history: list[dict], label: str) -> float:
    """
    Run the ML engine on real tx data to get a risk score.
    Falls back to label-based estimate if ML is unavailable.
    """
    from core.ml_engine import MLEngine
    try:
        ml = MLEngine()
        result = await ml.score(address, tx_history, neo4j_driver=None)
        score = result.score

        # Boost score for known attackers so they appear in anomaly panel
        if label == "attacker":
            score = min(1.0, score + 0.35)
        elif label == "bot":
            score = min(1.0, score + 0.15)

        return round(score, 4)
    except Exception as e:
        logger.warning("ML scoring failed for %s: %s — using label default", address[:10], e)
        defaults = {"attacker": 0.92, "bot": 0.72, "whale": 0.15, "exchange": 0.10, "defi_user": 0.25}
        return defaults.get(label, 0.40)


# ── Neo4j Write Helpers ───────────────────────────────────────────────────────

async def upsert_wallet(session, wallet: dict) -> None:
    """Write or update a Wallet node in Neo4j."""
    await session.run(
        """
        MERGE (w:Wallet {address: $address})
        SET w.label       = $label,
            w.risk_score  = $risk_score,
            w.flagged     = $flagged,
            w.tx_count    = $tx_count,
            w.balance_eth = $balance_eth,
            w.real_data   = true,
            w.last_seen   = datetime()
        """,
        address=wallet["address"].lower(),
        label=wallet["label"],
        risk_score=wallet["risk_score"],
        flagged=wallet["risk_score"] >= RISK_THRESHOLD,
        tx_count=wallet["tx_count"],
        balance_eth=wallet["balance_eth"],
    )


async def upsert_edges(session, address: str, normal_txs: list[dict], known_addresses: set) -> int:
    """
    Write SENT_TO edges between wallets that both exist in the graph.
    Only creates edges between known (seeded) addresses to keep graph clean.
    """
    edges_written = 0
    batch = []

    for tx in normal_txs:
        src = tx.get("from", "").lower()
        dst = tx.get("to", "").lower()
        if not src or not dst or src == dst:
            continue
        if src not in known_addresses or dst not in known_addresses:
            continue

        batch.append({
            "from":      src,
            "to":        dst,
            "tx_hash":   tx.get("hash", ""),
            "value_eth": tx.get("value_eth", 0.0),
            "gas_used":  tx.get("gas_used", 21_000),
            "timestamp": tx.get("timestamp", 0),
        })

    if batch:
        await session.run(
            """
            UNWIND $rels AS r
            MATCH (s:Wallet {address: r.from})
            MATCH (t:Wallet {address: r.to})
            MERGE (s)-[tx:SENT_TO {tx_hash: r.tx_hash}]->(t)
            SET tx.value_eth = r.value_eth,
                tx.gas_used  = r.gas_used,
                tx.timestamp = datetime({epochSeconds: toInteger(r.timestamp)})
            """,
            rels=batch,
        )
        edges_written = len(batch)

    return edges_written


# ── BFS Crawler ───────────────────────────────────────────────────────────────

async def bfs_crawl(
    seed_wallets: list[dict],
    depth: int = 1,
    max_wallets: int = 200,
) -> list[dict]:
    """
    BFS from seed wallets, expanding to counterparties at each depth level.
    Returns a flat list of wallet dicts with fetched on-chain data.
    """
    from core.etherscan import get_wallet_summary

    visited = {}   # address → wallet dict
    queue = list(seed_wallets)

    for current_depth in range(depth + 1):
        if not queue:
            break

        logger.info("BFS depth %d — processing %d wallets…", current_depth, len(queue))
        next_queue = []

        for seed in queue:
            address = seed["address"].lower()
            if address in visited:
                continue
            if len(visited) >= max_wallets:
                logger.info("Max wallets (%d) reached — stopping BFS.", max_wallets)
                break

            logger.info("  Fetching on-chain data for %s (%s)…",
                        address[:12] + "…", seed.get("label", "unknown"))

            try:
                summary = await get_wallet_summary(address, tx_limit=200)
                risk_score = await estimate_risk(
                    address, summary["tx_history"], seed.get("label", "unknown")
                )

                wallet = {
                    "address":    address,
                    "label":      seed.get("label", "defi_user"),
                    "hint":       seed.get("hint", ""),
                    "risk_score": risk_score,
                    "tx_count":   summary["tx_count"],
                    "balance_eth": summary["balance_eth"],
                    "tx_history": summary["tx_history"],
                    "normal_txs": summary["normal_txs"],
                    "counterparties": summary["counterparties"],
                }
                visited[address] = wallet

                # Queue counterparties for next depth level
                if current_depth < depth:
                    for cp in summary["counterparties"][:10]:   # max 10 neighbors per wallet
                        if cp.lower() not in visited:
                            next_queue.append({
                                "address": cp,
                                "label":   "unknown",
                                "hint":    f"Counterparty of {address[:10]}",
                            })

                logger.info("  ✅ %s | risk=%.3f | txs=%d | bal=%.4f ETH",
                            address[:14], risk_score, summary["tx_count"], summary["balance_eth"])

            except Exception as e:
                logger.warning("  ⚠️  Failed to fetch %s: %s", address[:12], e)
                continue

        queue = next_queue

    return list(visited.values())


# ── Main Seeding Coroutine ────────────────────────────────────────────────────

async def seed(
    reset: bool = False,
    depth: int = 1,
    max_wallets: int = 200,
    extra_seeds: list[str] | None = None,
) -> None:
    from database import apply_schema, get_driver, run_query

    driver = get_driver()
    t0 = time.time()

    # Optional reset
    if reset:
        logger.warning("⚠️  RESET flag — deleting all existing wallet data…")
        await run_query("MATCH (n:Wallet) DETACH DELETE n")
        logger.info("  Wallet nodes cleared.")

    # Apply schema constraints
    logger.info("Applying Neo4j schema…")
    await apply_schema()

    # Build seed list
    seeds = list(SEED_WALLETS)
    if extra_seeds:
        for addr in extra_seeds:
            seeds.append({"address": addr, "label": "unknown", "hint": "Custom seed"})

    logger.info("Starting BFS crawl — %d seeds, depth=%d, max=%d wallets",
                len(seeds), depth, max_wallets)

    # BFS crawl with Etherscan
    wallets = await bfs_crawl(seeds, depth=depth, max_wallets=max_wallets)

    if not wallets:
        logger.error("No wallets fetched — check your ETHERSCAN_API_KEY.")
        return

    # Write to Neo4j
    known_addresses = {w["address"] for w in wallets}
    total_edges = 0

    logger.info("Writing %d wallets to Neo4j…", len(wallets))
    async with driver.session() as session:
        for i, wallet in enumerate(wallets):
            await upsert_wallet(session, wallet)
            edges = await upsert_edges(session, wallet["address"], wallet["normal_txs"], known_addresses)
            total_edges += edges
            if (i + 1) % 10 == 0:
                logger.info("  Progress: %d / %d wallets written", i + 1, len(wallets))

    elapsed = time.time() - t0
    logger.info("✅ Real blockchain data seeded in %.1fs", elapsed)

    # ── Summary Report ────────────────────────────────────────────────────
    label_counts = Counter(w["label"] for w in wallets)
    flagged_count = sum(1 for w in wallets if w["risk_score"] >= RISK_THRESHOLD)
    avg_risk = sum(w["risk_score"] for w in wallets) / len(wallets)

    print("\n" + "=" * 60)
    print("  Third Eye — REAL BLOCKCHAIN SEED REPORT")
    print("=" * 60)
    print(f"  Network:              Ethereum Mainnet")
    print(f"  Total nodes:          {len(wallets):>8,}")
    print(f"  Total edges:          {total_edges:>8,}")
    print(f"  Flagged (risk>=0.75): {flagged_count:>8,}  ({flagged_count/len(wallets)*100:.1f}%)")
    print(f"  Avg risk score:       {avg_risk:>8.4f}")
    print(f"  Elapsed time:         {elapsed:>7.1f}s")
    print()
    print("  LABEL DISTRIBUTION")
    print("  " + "-" * 40)
    for label, count in sorted(label_counts.items(), key=lambda x: -x[1]):
        bar = "#" * int(count / len(wallets) * 40)
        print(f"  {label:<14} {count:>5,}  {count/len(wallets)*100:>5.1f}%  {bar}")
    print()
    print("  TOP RISK WALLETS")
    print("  " + "-" * 40)
    top_risk = sorted(wallets, key=lambda w: w["risk_score"], reverse=True)[:5]
    for w in top_risk:
        print(f"  {w['address'][:20]}...  risk={w['risk_score']:.4f}  [{w['label']}]")
        if w.get("hint"):
            print(f"    -> {w['hint']}")
    print("=" * 60 + "\n")

    await driver.close()


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Third Eye — Real Blockchain Neo4j Seeder (Etherscan)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/seed_real.py                         # Seed from curated list, depth=1
  python scripts/seed_real.py --depth 2               # BFS depth 2 (more data, slower)
  python scripts/seed_real.py --max-wallets 50        # Quick test with 50 wallets
  python scripts/seed_real.py --reset                 # Wipe existing data first
  python scripts/seed_real.py --extra 0xABC...        # Add custom seed address
        """,
    )
    parser.add_argument("--depth",       type=int,  default=1,   help="BFS crawl depth (default: 1)")
    parser.add_argument("--max-wallets", type=int,  default=200, help="Max wallets to seed (default: 200)")
    parser.add_argument("--reset",       action="store_true",    help="Delete all existing :Wallet nodes first")
    parser.add_argument("--extra",       nargs="*", default=[],  help="Extra seed wallet addresses")

    args = parser.parse_args()

    asyncio.run(seed(
        reset=args.reset,
        depth=args.depth,
        max_wallets=args.max_wallets,
        extra_seeds=args.extra,
    ))
