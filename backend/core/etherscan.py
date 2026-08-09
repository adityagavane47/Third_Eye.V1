"""
backend/core/etherscan.py — Async Etherscan API Client
Third Eye — Real On-Chain Data Layer

Fetches real Ethereum transaction data for wallet risk analysis.
Rate-limited to 5 req/s to respect Etherscan free-tier limits.
"""

import asyncio
import logging
import os
import time
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("Third Eye.etherscan")

ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
ETHERSCAN_NETWORK = os.getenv("ETHERSCAN_NETWORK", "mainnet")

NETWORK_URLS = {
    "mainnet":    ("https://api.etherscan.io/v2/api", 1),
    "sepolia":    ("https://api.etherscan.io/v2/api", 11155111),
    "base":       ("https://api.etherscan.io/v2/api", 8453),
    "base-sepolia": ("https://api.etherscan.io/v2/api", 84532),
}

_network_cfg = NETWORK_URLS.get(ETHERSCAN_NETWORK, NETWORK_URLS["mainnet"])
BASE_URL, CHAIN_ID = _network_cfg

# Free tier: 5 calls/sec — we stay at 4 to be safe
_RATE_LIMIT_DELAY = 0.25   # seconds between requests
_last_request_time: float = 0.0
_lock = asyncio.Lock()


async def _throttled_get(client: httpx.AsyncClient, params: dict) -> dict:
    """Enforce rate limiting and execute a GET request."""
    global _last_request_time
    async with _lock:
        now = time.monotonic()
        wait = _RATE_LIMIT_DELAY - (now - _last_request_time)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request_time = time.monotonic()

    params["apikey"] = ETHERSCAN_API_KEY
    params["chainid"] = CHAIN_ID
    try:
        resp = await client.get(BASE_URL, params=params, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "0" and data.get("message") not in ("No transactions found", "No records found"):
            logger.warning("Etherscan API warning: %s — %s", data.get("message"), data.get("result"))
        return data
    except httpx.HTTPStatusError as e:
        logger.error("Etherscan HTTP error: %s", e)
        return {"status": "0", "result": []}
    except Exception as e:
        logger.error("Etherscan request failed: %s", e)
        return {"status": "0", "result": []}


def _normalize_tx(raw: dict) -> dict:
    """Convert a raw Etherscan tx dict into the internal format used by MLEngine."""
    try:
        value_wei = int(raw.get("value", 0))
        value_eth = value_wei / 1e18
    except (ValueError, TypeError):
        value_eth = 0.0

    try:
        gas_used = int(raw.get("gasUsed", raw.get("gas", 21_000)))
    except (ValueError, TypeError):
        gas_used = 21_000

    return {
        "hash":      raw.get("hash", ""),
        "from":      raw.get("from", "").lower(),
        "to":        (raw.get("to") or "").lower(),
        "value_eth": round(value_eth, 6),
        "gas_used":  gas_used,
        "timestamp": int(raw.get("timeStamp", 0)),
        "is_error":  raw.get("isError", "0") == "1",
        "input":     raw.get("input", "0x"),
    }


async def get_normal_transactions(
    address: str,
    limit: int = 200,
    start_block: int = 0,
) -> list[dict]:
    """
    Fetch normal ETH transfer transactions for a wallet.
    Returns up to `limit` most recent transactions.
    """
    address = address.lower()
    async with httpx.AsyncClient() as client:
        data = await _throttled_get(client, {
            "module":     "account",
            "action":     "txlist",
            "address":    address,
            "startblock": start_block,
            "endblock":   99999999,
            "page":       1,
            "offset":     min(limit, 10_000),
            "sort":       "desc",
        })

    results = data.get("result", [])
    if not isinstance(results, list):
        return []

    txs = [_normalize_tx(r) for r in results[:limit]]
    logger.info("Fetched %d normal txs for %s", len(txs), address[:10])
    return txs


async def get_internal_transactions(
    address: str,
    limit: int = 100,
) -> list[dict]:
    """
    Fetch internal transactions (contract calls, flash loans, reentrancy).
    These are critical for detecting DeFi exploits.
    """
    address = address.lower()
    async with httpx.AsyncClient() as client:
        data = await _throttled_get(client, {
            "module":  "account",
            "action":  "txlistinternal",
            "address": address,
            "page":    1,
            "offset":  min(limit, 10_000),
            "sort":    "desc",
        })

    results = data.get("result", [])
    if not isinstance(results, list):
        return []

    txs = [_normalize_tx(r) for r in results[:limit]]
    logger.info("Fetched %d internal txs for %s", len(txs), address[:10])
    return txs


async def get_erc20_transfers(
    address: str,
    limit: int = 100,
) -> list[dict]:
    """
    Fetch ERC-20 token transfer events.
    Large token movements correlate with DeFi exploits.
    """
    address = address.lower()
    async with httpx.AsyncClient() as client:
        data = await _throttled_get(client, {
            "module":  "account",
            "action":  "tokentx",
            "address": address,
            "page":    1,
            "offset":  min(limit, 10_000),
            "sort":    "desc",
        })

    results = data.get("result", [])
    if not isinstance(results, list):
        return []

    transfers = []
    for r in results[:limit]:
        try:
            decimals = int(r.get("tokenDecimal", 18))
            raw_value = int(r.get("value", 0))
            value_tokens = raw_value / (10 ** decimals)
        except (ValueError, TypeError):
            value_tokens = 0.0

        transfers.append({
            "hash":          r.get("hash", ""),
            "from":          (r.get("from") or "").lower(),
            "to":            (r.get("to") or "").lower(),
            "token_symbol":  r.get("tokenSymbol", "???"),
            "token_name":    r.get("tokenName", ""),
            "value_tokens":  round(value_tokens, 4),
            "contract":      (r.get("contractAddress") or "").lower(),
            "timestamp":     int(r.get("timeStamp", 0)),
        })

    logger.info("Fetched %d ERC-20 transfers for %s", len(transfers), address[:10])
    return transfers


async def get_eth_balance(address: str) -> float:
    """Fetch current ETH balance in Ether (not Wei)."""
    address = address.lower()
    async with httpx.AsyncClient() as client:
        data = await _throttled_get(client, {
            "module":  "account",
            "action":  "balance",
            "address": address,
            "tag":     "latest",
        })

    result = data.get("result", "0")
    try:
        return int(result) / 1e18
    except (ValueError, TypeError):
        return 0.0


async def get_wallet_summary(
    address: str,
    tx_limit: int = 200,
) -> dict[str, Any]:
    """
    Convenience function: fetch all data for a wallet in parallel.
    Returns a unified dict ready for MLEngine.extract_features().

    Fires 3 API calls concurrently (normal txs, internal txs, ERC-20 transfers).
    """
    address = address.lower()
    logger.info("Fetching full wallet summary for %s…", address[:10])

    # Fire requests with small delays to stay under rate limit
    normal_txs, balance = await asyncio.gather(
        get_normal_transactions(address, limit=tx_limit),
        get_eth_balance(address),
    )

    # Fetch internal txs separately (rate limit)
    await asyncio.sleep(_RATE_LIMIT_DELAY)
    internal_txs = await get_internal_transactions(address, limit=50)

    # Merge normal + internal into unified tx_history for MLEngine
    combined_txs = normal_txs + [
        {**t, "gas_used": max(t["gas_used"], 400_000)}   # internal txs flag high gas
        for t in internal_txs
    ]

    # Derive unique counterparties
    counterparties = set()
    for tx in normal_txs:
        if tx["to"] and tx["to"] != address:
            counterparties.add(tx["to"])
        if tx["from"] and tx["from"] != address:
            counterparties.add(tx["from"])

    return {
        "address":        address,
        "balance_eth":    round(balance, 4),
        "tx_count":       len(normal_txs),
        "internal_count": len(internal_txs),
        "counterparties": list(counterparties),
        "tx_history":     combined_txs,         # → MLEngine.extract_features()
        "normal_txs":     normal_txs,            # → Neo4j SENT_TO edges
    }


async def resolve_counterparties(
    addresses: list[str],
    max_wallets: int = 50,
) -> list[str]:
    """
    Given a list of counterparty addresses, filter to those that look like
    EOA wallets (not contracts) by checking tx count > 0.
    Used by the BFS crawler in seed_real.py.
    """
    wallets = []
    async with httpx.AsyncClient() as client:
        for addr in addresses[:max_wallets]:
            data = await _throttled_get(client, {
                "module":  "account",
                "action":  "txlist",
                "address": addr,
                "page":    1,
                "offset":  1,
                "sort":    "desc",
            })
            results = data.get("result", [])
            if isinstance(results, list) and len(results) > 0:
                wallets.append(addr)

    return wallets
