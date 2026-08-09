"""
backend/main.py — Third Eye FastAPI Entry Point
"""

import hashlib
import hmac
import logging
import os
import random
import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("Third Eye.main")

HMAC_SECRET = os.getenv("HMAC_SECRET_KEY", "").encode()
CORS_ORIGINS = os.getenv("API_CORS_ORIGINS", "http://localhost:5173").split(",")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from database import get_driver
    logger.info("🛡️  Third Eye API starting up…")
    app.state.neo4j = get_driver()

    try:
        await app.state.neo4j.verify_connectivity()
        logger.info("✅ Neo4j connection verified")
        # Clean up previous demo exploits only if connected
        async with app.state.neo4j.session() as session:
            await session.run("MATCH (w:Wallet {injected: true}) DETACH DELETE w")
    except Exception as e:
        logger.warning(f"⚠️  Neo4j unavailable at startup (will retry on first request): {e}")

    yield
    logger.info("🔴  Third Eye API shutting down…")
    await app.state.neo4j.close()



app = FastAPI(
    title="Third Eye API",
    description="On-Chain Immunity System — Backend Data & AI Layer",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class HMACValidationMiddleware:
    """
    Validates X-Third Eye-Signature header on internal service routes (/internal/*).
    Signature format: HMAC-SHA256(secret, f"{method}:{path}:{timestamp}:{body_hex}")
    Header format:    "t=<unix_ts>,v1=<hex_signature>"
    Replay window:    300 seconds
    """

    INTERNAL_PREFIX = "/internal"
    REPLAY_WINDOW_S = 300

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        path = request.url.path

        if path.startswith(self.INTERNAL_PREFIX):
            error = await self._validate(request)
            if error:
                response = JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": error},
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)

    async def _validate(self, request: Request) -> str | None:
        header = request.headers.get("X-Third Eye-Signature", "")
        if not header:
            return "Missing X-Third Eye-Signature header"

        try:
            parts = dict(p.split("=", 1) for p in header.split(","))
            timestamp = int(parts["t"])
            provided_sig = parts["v1"]
        except (KeyError, ValueError):
            return "Malformed X-Third Eye-Signature header"

        # Replay attack prevention
        if abs(time.time() - timestamp) > self.REPLAY_WINDOW_S:
            return "Signature timestamp outside replay window"

        body = await request.body()
        payload = f"{request.method}:{request.url.path}:{timestamp}:{body.hex()}"
        expected_sig = hmac.new(HMAC_SECRET, payload.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(expected_sig, provided_sig):
            return "Invalid HMAC signature"

        return None


app.add_middleware(HMACValidationMiddleware)


@app.get("/api/health", tags=["System"])
async def health_check():
    """Liveness probe for load balancers and CI pipelines."""
    return {"status": "ok", "service": "Third Eye-galaxy-api", "version": "1.0.0"}


@app.get("/api/graph/nodes", tags=["Graph"])
async def get_graph_nodes(limit: int = 200, request: Request = None):
    """Fetch wallet nodes and relationships for 3D graph."""
    driver = request.app.state.neo4j
    async with driver.session() as session:
        nodes_result = await session.run(
            """
            MATCH (w:Wallet)
            WITH w
            ORDER BY w.risk_score DESC
            LIMIT 40
            OPTIONAL MATCH (w)-[:SENT_TO]-(neighbor:Wallet)
            WITH collect(w) + collect(neighbor) AS raw_nodes
            UNWIND raw_nodes AS n
            WITH DISTINCT n
            WHERE n IS NOT NULL
            LIMIT $limit
            RETURN
                n.address    AS address,
                n.label      AS label,
                n.risk_score AS riskScore,
                n.flagged    AS flagged,
                n.tx_count   AS txCount,
                n.balance_eth AS balanceEth
            """,
            limit=limit,
        )
        nodes_data = await nodes_result.data()

        nodes = []
        addresses = []
        for row in nodes_data:
            addr = row["address"]
            if not addr:
                continue
            addresses.append(addr)
            nodes.append({
                "id":         addr,
                "address":    addr,
                "label":      row["label"]     or "unknown",
                "riskScore":  float(row["riskScore"] or 0.0),
                "flagged":    bool(row["flagged"]   or False),
                "txCount":    int(row["txCount"]    or 0),
                "balanceEth": float(row["balanceEth"] or 0.0),
            })

        if addresses:
            links_result = await session.run(
                """
                UNWIND $addresses AS addr
                MATCH (s:Wallet {address: addr})-[r:SENT_TO]->(t:Wallet)
                WHERE t.address IN $addresses
                RETURN
                    s.address  AS source,
                    t.address  AS target,
                    r.tx_hash  AS txHash,
                    r.value_eth AS valueEth
                """,
                addresses=addresses,
            )
            links_data = await links_result.data()
        else:
            links_data = []

    return {"nodes": nodes, "links": links_data}


class FlagWalletRequest(BaseModel):
    wallet_address: str
    risk_score: float


@app.post("/api/graph/flag", tags=["Graph"])
async def flag_wallet(body: FlagWalletRequest, request: Request = None):
    driver = request.app.state.neo4j
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (w:Wallet {address: $address})
            SET
                w.flagged       = true,
                w.risk_score    = $risk_score,
                w.last_analyzed = datetime()
            RETURN w.address AS address, w.risk_score AS risk_score, w.flagged AS flagged
            """,
            address=body.wallet_address,
            risk_score=body.risk_score,
        )
        row = await result.single()

    if not row:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": f"Wallet {body.wallet_address} not found in graph."},
        )

    return {
        "flagged":     row["flagged"],
        "address":     row["address"],
        "risk_score":  row["risk_score"],
        "status":      "updated",
    }


@app.get("/api/forensic/report/{wallet_address}", tags=["AI Forensics"])
async def get_forensic_report(wallet_address: str, request: Request = None):
    from agent.llm_engine import generate_forensic_report
    risk_score = 0.75
    label = "unknown"
    try:
        driver = request.app.state.neo4j
        async with driver.session() as session:
            result = await session.run(
                "MATCH (w:Wallet {address: $addr}) RETURN w.risk_score AS rs, w.label AS lbl LIMIT 1",
                addr=wallet_address,
            )
            row = await result.single()
            if row:
                risk_score = row["rs"] or 0.75
                label = row["lbl"] or "unknown"
    except Exception:
        pass

    report = await generate_forensic_report(
        wallet_address=wallet_address,
        risk_score=risk_score,
        label=label,
    )
    return report


@app.post("/api/simulate-exploit", tags=["Simulation"])
async def simulate_exploit(request: Request = None):
    import secrets
    import random
    from agent.llm_engine import generate_forensic_report
    from core.ml_engine import MLEngine

    attacker_address = "0x" + secrets.token_hex(20)
    tx_count = random.randint(120, 200)
    tx_history = []
    for i in range(tx_count):
        tx_history.append({
            "to": "0x" + secrets.token_hex(20)[:10] + "...",
            "value_eth": random.uniform(0.1, 50.0),
            "gas_used": 500_000 if i % 10 == 0 else 21_000,
        })

    ml = MLEngine()
    normal_features = [[5.0, 1.0, 2.0, 0.0, 0.0, 0.1, 0.0, 0.0, 0.0, 0.1] for _ in range(10)]
    ml._model.train(normal_features)
    ml_result = await ml.score(attacker_address, tx_history)
    
    dynamic_risk_score = min(0.99, ml_result.score + 0.40) 
    dynamic_risk_hints = ml_result.risk_hints

    driver = request.app.state.neo4j
    async with driver.session() as session:
        # Clear previous injected attackers

        await session.run("MATCH (w:Wallet {injected: true}) DETACH DELETE w")

        await session.run(
            """
            MERGE (w:Wallet {address: $address})
            SET w.label      = 'attacker',
                w.risk_score  = $risk_score,
                w.flagged     = true,
                w.tx_count    = $tx_count,
                w.balance_eth = $balance,
                w.injected    = true,
                w.last_seen   = datetime()
            """,
            address=attacker_address,
            risk_score=dynamic_risk_score,
            tx_count=tx_count,
            balance=round(sum(t["value_eth"] for t in tx_history) * 0.01, 4),
        )

        victims_result = await session.run(
            "MATCH (w:Wallet) WHERE w.address <> $addr RETURN w.address AS addr ORDER BY rand() LIMIT 3",
            addr=attacker_address,
        )
        victims = [r["addr"] async for r in victims_result]

        for victim in victims:
            tx_hash = "0x" + secrets.token_hex(32)
            await session.run(
                """
                MATCH (a:Wallet {address: $attacker})
                MATCH (v:Wallet {address: $victim})
                MERGE (a)-[r:SENT_TO {tx_hash: $tx_hash}]->(v)
                SET r.value_eth = $value, r.gas_used = $gas,
                    v.flagged = true,
                    v.risk_score = 0.88,
                    v.injected = true
                """,
                attacker=attacker_address,
                victim=victim,
                tx_hash=tx_hash,
                value=round(random.uniform(10, 100), 4),
                gas=random.randint(150_000, 500_000),
            )

    logger.warning("🚨 Exploit simulated — attacker wallet injected: %s", attacker_address)

    report = await generate_forensic_report(
        wallet_address=attacker_address,
        risk_score=dynamic_risk_score,
        label="attacker",
        risk_hints=dynamic_risk_hints,
    )

    return {
        "attacker_address": attacker_address,
        "ml_score": dynamic_risk_score,
        "victims": victims,
        "report": report,
    }


@app.get("/api/anomalies", tags=["Detection"])
async def list_anomalies(min_risk: float = 0.7, request: Request = None):
    driver = request.app.state.neo4j
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (w:Wallet)
            WHERE w.risk_score >= $min_risk
            RETURN
                w.address     AS address,
                w.label       AS label,
                w.risk_score  AS riskScore,
                w.flagged     AS flagged,
                w.tx_count    AS txCount,
                w.balance_eth AS balanceEth
            ORDER BY w.risk_score DESC
            LIMIT 100
            """,
            min_risk=min_risk,
        )
        rows = await result.data()

    anomalies = [
        {
            "address":    r["address"],
            "label":      r["label"]     or "unknown",
            "riskScore":  float(r["riskScore"] or 0.0),
            "flagged":    bool(r["flagged"]   or False),
            "txCount":    int(r["txCount"]    or 0),
            "balanceEth": float(r["balanceEth"] or 0.0),
        }
        for r in rows
    ]

    return {
        "anomalies":  anomalies,
        "count":      len(anomalies),
        "threshold":  min_risk,
    }


class ShieldRequest(BaseModel):
    wallet_address: str
    risk_score: float
    reason: str = "Automated detection by Third Eye"


@app.post("/api/shield/blacklist", tags=["Shield"])
async def shield_blacklist(body: ShieldRequest):
    """Backend-signed blacklist call using OPERATOR_PRIVATE_KEY."""
    import asyncio
    import httpx
    from eth_account import Account
    from eth_abi import encode as abi_encode

    # Validate address before touching ABI encoder
    import re
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", body.wallet_address):
        return JSONResponse(
            status_code=400,
            content={"detail": f"Invalid wallet address: '{body.wallet_address}'. Must be 0x + 40 hex chars."},
        )

    rpc_url = os.getenv("WEB3_RPC_URL", "https://sepolia.base.org")
    priv_key = os.getenv("OPERATOR_PRIVATE_KEY")
    contract_addr = os.getenv("GUARDIAN_CONTRACT_ADDRESS", "0xd9145CCE52D386f254917e481eB44e9943F39138")

    if not priv_key:
        return JSONResponse(status_code=503, content={"detail": "OPERATOR_PRIVATE_KEY not set"})

    try:
        from eth_utils import keccak
        fn_sig = b"blacklistWallet(address,uint256,string)"
        selector = keccak(fn_sig)[:4]
        risk_uint = int(body.risk_score * 1000)
        encoded_args = abi_encode(["address", "uint256", "string"], [body.wallet_address, risk_uint, body.reason])
        calldata = "0x" + selector.hex() + encoded_args.hex()

        account = Account.from_key(priv_key)

        async with httpx.AsyncClient(timeout=30) as client:
            async def rpc(method, params):
                r = await client.post(rpc_url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
                res = r.json()
                if "error" in res:
                    raise Exception(f"RPC Error ({method}): {res['error'].get('message', 'Unknown error')}")
                return res

            res_nonce = await rpc("eth_getTransactionCount", [account.address, "latest"])
            nonce = int(res_nonce["result"], 16)
            
            res_gas = await rpc("eth_gasPrice", [])
            gas_price = int(res_gas["result"], 16)
            
            res_chain = await rpc("eth_chainId", [])
            chain_id = int(res_chain["result"], 16)

            tx = {
                "nonce":    nonce,
                "gasPrice": gas_price,
                "gas":      200000,
                "to":       contract_addr,
                "value":    0,
                "data":     calldata,
                "chainId":  chain_id,
            }
            signed = account.sign_transaction(tx)
            raw_tx_hex = signed.raw_transaction.hex()
            if not raw_tx_hex.startswith("0x"):
                raw_tx_hex = "0x" + raw_tx_hex
            
            send_res = await rpc("eth_sendRawTransaction", [raw_tx_hex])
            tx_hash = send_res["result"]

            block_number = None
            for _ in range(30):
                await asyncio.sleep(2)
                res_receipt = await rpc("eth_getTransactionReceipt", [tx_hash])
                receipt = res_receipt.get("result")
                if receipt:
                    block_number = int(receipt["blockNumber"], 16)
                    if int(receipt.get("status", "0x0"), 16) == 0:
                        raise Exception("Transaction reverted on-chain (check operator role)")
                    break

        logger.info(f"Shield confirmed for {body.wallet_address}: tx={tx_hash}, block={block_number}")
        return {
            "status":         "blacklisted",
            "wallet_address": body.wallet_address,
            "tx_hash":        tx_hash,
            "block_number":   block_number,
            "risk_score":     body.risk_score,
        }
    except Exception as exc:
        err_msg = str(exc)
        if "replacement transaction underpriced" in err_msg or "nonce too low" in err_msg:
            logger.warning(f"Duplicate shield request for {body.wallet_address} ignored (already pending).")
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={"detail": "A shield request is already pending. Please wait for it to confirm."},
            )
            
        logger.error(f"Shield blacklist failed: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": str(exc)},
        )


# ── Real Blockchain Ingestion ────────────────────────────────────────────────

class IngestWalletRequest(BaseModel):
    address: str
    label: str = "unknown"


@app.post("/api/ingest/wallet", tags=["Ingestion"])
async def ingest_wallet(body: IngestWalletRequest, request: Request = None):
    """
    Fetch real on-chain data for a wallet address from Etherscan,
    run ML risk scoring, and upsert the wallet + edges into Neo4j.

    This is the live import path — any Ethereum address can be analysed in real time.
    """
    from core.etherscan import get_wallet_summary
    from core.ml_engine import MLEngine

    address = body.address.strip().lower()
    if not address.startswith("0x") or len(address) != 42:
        return JSONResponse(
            status_code=400,
            content={"detail": "Invalid Ethereum address format. Expected 0x + 40 hex chars."},
        )

    logger.info("Ingesting real wallet: %s", address)

    # 1. Fetch on-chain data from Etherscan
    try:
        summary = await get_wallet_summary(address, tx_limit=200)
    except Exception as exc:
        logger.error("Etherscan fetch failed for %s: %s", address, exc)
        return JSONResponse(
            status_code=503,
            content={"detail": f"Etherscan fetch failed: {str(exc)}. Check ETHERSCAN_API_KEY."},
        )

    # 2. Run ML scoring on real tx history
    ml = MLEngine()
    driver = request.app.state.neo4j
    risk_obj = await ml.score(
        wallet_address=address,
        tx_history=summary["tx_history"],
        neo4j_driver=driver,
    )

    risk_score = risk_obj.score
    if body.label == "attacker":
        risk_score = min(1.0, risk_score + 0.35)

    # 3. Upsert wallet node into Neo4j
    async with driver.session() as session:
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
            address=address,
            label=body.label,
            risk_score=round(risk_score, 4),
            flagged=risk_score >= 0.75,
            tx_count=summary["tx_count"],
            balance_eth=summary["balance_eth"],
        )

        # 4. Write SENT_TO edges for counterparties already in the graph
        existing = await session.run("MATCH (w:Wallet) RETURN w.address AS addr")
        existing_addrs = {r["addr"] async for r in existing}

        edges_written = 0
        edge_batch = []
        for tx in summary["normal_txs"]:
            src = (tx.get("from") or "").lower()
            dst = (tx.get("to") or "").lower()
            if not src or not dst or src == dst:
                continue
            if src not in existing_addrs and dst not in existing_addrs:
                continue
            edge_batch.append({
                "from":      src,
                "to":        dst,
                "tx_hash":   tx.get("hash", ""),
                "value_eth": tx.get("value_eth", 0.0),
                "gas_used":  tx.get("gas_used", 21_000),
                "timestamp": tx.get("timestamp", 0),
            })

        if edge_batch:
            await session.run(
                """
                UNWIND $rels AS r
                MERGE (s:Wallet {address: r.from})
                MERGE (t:Wallet {address: r.to})
                MERGE (s)-[tx:SENT_TO {tx_hash: r.tx_hash}]->(t)
                SET tx.value_eth = r.value_eth,
                    tx.gas_used  = r.gas_used,
                    tx.timestamp = datetime({epochSeconds: toInteger(r.timestamp)})
                """,
                rels=edge_batch[:500],   # cap at 500 edges per ingest
            )
            edges_written = len(edge_batch)

    logger.info(
        "Ingest complete: %s | risk=%.3f | txs=%d | edges=%d",
        address, risk_score, summary["tx_count"], edges_written,
    )

    return {
        "address":       address,
        "risk_score":    round(risk_score, 4),
        "risk_level":    "HIGH" if risk_score >= 0.75 else "MEDIUM" if risk_score >= 0.40 else "LOW",
        "flagged":       risk_score >= 0.75,
        "risk_hints":    risk_obj.risk_hints,
        "tx_count":      summary["tx_count"],
        "balance_eth":   summary["balance_eth"],
        "edges_written": edges_written,
        "node_created":  True,
        "source":        "etherscan_mainnet",
    }
