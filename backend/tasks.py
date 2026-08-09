"""
backend/tasks.py — Celery Background Task Queue
Role: AI Analyst (Member 1)

Celery tasks run anomaly detection and forensic analysis asynchronously
so the FastAPI response layer stays non-blocking.

Task pipeline:
    trigger_anomaly_scan(wallet_address)
        │
        ├─► ml_engine.score() → RiskScore
        ├─► psi_engine.match() → [SignatureMatch]
        ├─► forensic_agent.analyze() → ForensicReport  [if risk > threshold]
        └─► audit_logger.log_anomaly()
"""

import asyncio
import logging
import os

from celery import Celery
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("Third Eye.tasks")

CELERY_BROKER = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

RISK_THRESHOLD_FORENSIC = 0.65   # Only call Gemini if score exceeds this
RISK_THRESHOLD_SHIELD = 0.90     # Auto-shield flag threshold

# ── Celery App ───────────────────────────────────────────────
celery_app = Celery(
    "Third Eye_galaxy",
    broker=CELERY_BROKER,
    backend=CELERY_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,           # Re-queue on worker crash
    worker_prefetch_multiplier=1,  # Fair task distribution
    beat_schedule={
        # Periodic full-graph sweep every 10 minutes
        "sweep-galaxy-every-10-min": {
            "task": "tasks.sweep_galaxy",
            "schedule": 600.0,
        },
    },
)


# ── Helper: run async functions inside Celery (sync) tasks ───
def run_async(coro):
    """Bridge async coroutines into Celery's synchronous task context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Task: Analyze a Single Wallet ───────────────────────────
@celery_app.task(
    bind=True,
    name="tasks.analyze_wallet",
    max_retries=3,
    default_retry_delay=30,
    soft_time_limit=120,
    time_limit=180,
)
def analyze_wallet(self, wallet_address: str, tx_history: list[dict] | None = None):
    """
    Full anomaly detection pipeline for a single wallet.

    Triggered by:
    - FastAPI endpoint: POST /api/graph/flag
    - Periodic sweep: tasks.sweep_galaxy
    - Real-time ingestor: on new block with suspicious patterns

    Args:
        wallet_address: 0x... wallet to analyze
        tx_history:     Optional pre-fetched tx list (avoids duplicate DB call)

    Returns:
        dict with wallet_address, risk_score, risk_level, and report summary
    """
    logger.info("Task analyze_wallet started: %s", wallet_address)

    try:
        # ── Step 1: ML Scoring ───────────────────────────────
        from core.ml_engine import MLEngine
        from core.psi_engine import PSIEngine

        ml  = MLEngine()
        psi = PSIEngine()

        # Load PSI blacklist from flagged wallets (best-effort, no driver in Celery)
        # In production: inject driver via app.state or a dedicated DB connection
        tx_history = tx_history or []

        # ── Step 1: Async ML Scoring (run in sync context via bridge) ─
        risk_score_obj = run_async(
            ml.score(
                wallet_address=wallet_address,
                tx_history=tx_history,
                neo4j_driver=None,   # No live driver in Celery — graph features skipped
            )
        )

        # ── Step 2: PSI Pattern Matching ─────────────────────
        related_addrs = list({t.get("to", "") for t in tx_history if t.get("to")})
        sig_matches = psi.match(wallet_address, tx_history, related_addresses=related_addrs)
        sig_dicts = [
            {
                "id":          m.signature_id,
                "name":        m.category.value,
                "description": m.description,
                "confidence":  m.confidence,
            }
            for m in sig_matches
        ]
        psi_hints = [
            f"[{m.category.value.upper()}] {m.description} (conf={m.confidence:.0%})"
            for m in sig_matches
        ]
        combined_hints = risk_score_obj.risk_hints + psi_hints

        # ── Step 3: Audit the detection ──────────────────────
        from core.audit import audit_logger
        audit_logger.log_anomaly(
            wallet=wallet_address,
            risk_score=risk_score_obj.score,
            hints=combined_hints,
        )


        result = {
            "wallet_address":     wallet_address,
            "risk_score":         risk_score_obj.score,
            "confidence":         risk_score_obj.confidence,
            "risk_hints":         combined_hints,
            "signature_matches":  sig_dicts,
            "forensic_report":    None,
        }

        # ── Step 4: Gemini Forensic Analysis (conditional) ───
        if risk_score_obj.score >= RISK_THRESHOLD_FORENSIC:
            logger.info(
                "Risk %.3f >= threshold %.2f — triggering ForensicAgent for %s",
                risk_score_obj.score, RISK_THRESHOLD_FORENSIC, wallet_address,
            )
            from agent.forensic_agent import ForensicAgent
            agent = ForensicAgent()
            report = run_async(
                agent.analyze(
                    wallet_address=wallet_address,
                    risk_score=risk_score_obj.score,
                    confidence=risk_score_obj.confidence,
                    risk_hints=risk_score_obj.risk_hints,
                    signature_matches=sig_dicts,
                    label="unknown",
                )
            )
            result["forensic_report"] = {
                "risk_level":          report.risk_level,
                "executive_summary":   report.executive_summary,
                "threat_narrative":    report.threat_narrative,
                "recommended_actions": report.recommended_actions,
                "exploit_categories":  report.exploit_categories,
            }
            audit_logger.log_forensic_report(wallet_address, report.executive_summary)


        # ── Step 5: Persist results back to Neo4j ─────────────
        is_flagged = risk_score_obj.score >= 0.75
        from database import run_query
        run_async(
            run_query(
                """
                MATCH (w:Wallet {address: $address})
                SET w.risk_score = $risk_score,
                    w.flagged = $flagged
                """,
                {
                    "address": wallet_address,
                    "risk_score": risk_score_obj.score,
                    "flagged": is_flagged,
                }
            )
        )

        # ── Step 6: Auto-shield flag (very high risk) ─────────
        if risk_score_obj.score >= RISK_THRESHOLD_SHIELD:
            logger.warning(
                "🚨 Auto-shield flag: %s (score=%.3f)",
                wallet_address,
                risk_score_obj.score,
            )
            # TODO (Member 2): Trigger useShield / Guardian contract call
            # shield_wallet.delay(wallet_address)
            result["auto_shield_flagged"] = True

        logger.info("Task analyze_wallet complete: %s → %.3f", wallet_address, risk_score_obj.score)
        return result

    except Exception as exc:
        logger.error("Task failed for %s: %s", wallet_address, exc, exc_info=True)
        raise self.retry(exc=exc)


# ── Task: Periodic Full-Galaxy Sweep ────────────────────────
@celery_app.task(name="tasks.sweep_galaxy")
def sweep_galaxy():
    """
    Scheduled task: fetch all unanalyzed wallet nodes from Neo4j
    and enqueue analyze_wallet tasks for each.

    TODO (Member 1):
    - Query Neo4j for wallets where last_analyzed IS NULL or > 1 hour ago
    - Batch enqueue analyze_wallet tasks
    - Update Neo4j with sweep timestamp
    """
    logger.info("sweep_galaxy task started")
    from database import run_query

    # Atomic read-and-update to prevent multiple workers from picking up the same wallets
    cypher = """
        MATCH (w:Wallet)
        WHERE w.last_analyzed IS NULL OR w.last_analyzed < datetime() - duration('PT1H')
        WITH w LIMIT 500
        SET w.last_analyzed = datetime()
        RETURN w.address AS address
    """
    
    wallets = run_async(run_query(cypher))
    
    for row in wallets:
        addr = row.get("address")
        if addr:
            analyze_wallet.delay(addr)
            
    logger.info("sweep_galaxy complete: queued %d wallets for analysis", len(wallets))
    return {"status": "swept", "wallets_queued": len(wallets)}


# ── Task: Shield Activation (Web3 Enforcer handoff) ─────────
@celery_app.task(name="tasks.shield_wallet")
def shield_wallet(wallet_address: str):
    """
    Emits an event for the Web3 Enforcer (Member 2) to call
    ThirdEyeGuardian.sol's shield function on-chain.

    TODO (Member 2): Implement contract call via ethers.js / web3.py
    """
    logger.info("shield_wallet task triggered for %s", wallet_address)
    # TODO (Member 2): Use ethers/web3.py to call Guardian contract
    from core.audit import audit_logger
    audit_logger.log_shield(wallet_address, tx_hash="0x_pending", triggered_by="celery")
    return {"wallet": wallet_address, "status": "shield_queued"}
