"""
backend/core/audit.py — Third Eye WORM Audit Trail
Ported from ThirdEye audit.py (Write-Once-Read-Many compliant logging)

All entries are append-only JSON lines — no record is ever modified or deleted.
SHA-256 checksums are computed per entry for tamper detection.
"""

import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

logger = logging.getLogger("Third Eye.audit")

# ── File Paths ────────────────────────────────────────────────────
WORM_LOG_FILE = Path(os.getenv("AUDIT_LOG_PATH", "logs/ThirdEye_audit_worm.log"))

# ── Event Types ───────────────────────────────────────────────────
class EventType(str, Enum):
    # ── Ported from ThirdEye ──────────────────────────────────
    API_INGESTION           = "API_INGESTION"       # New blockchain data ingested
    EPOCH_ROTATION          = "EPOCH_ROTATION"       # ML model epoch / weight rotation
    THREAT_ALERT            = "THREAT_ALERT"         # High-severity threat raised

    # ── Third Eye extensions ──────────────────────────
    ANOMALY_DETECTED        = "ANOMALY_DETECTED"
    FORENSIC_REPORT         = "FORENSIC_REPORT"
    SHIELD_ACTIVATED        = "SHIELD_ACTIVATED"
    WALLET_BLACKLISTED      = "WALLET_BLACKLISTED"
    WALLET_WHITELISTED      = "WALLET_WHITELISTED"
    PSI_MATCH               = "PSI_MATCH"
    SYSTEM_STARTUP          = "SYSTEM_STARTUP"


# ── WORM Entry & Checksum ─────────────────────────────────────────
@dataclass
class AuditEvent:
    """Immutable WORM audit record — never modified after creation."""
    event_type: EventType
    wallet_address: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    risk_score: float | None = None
    details: dict = field(default_factory=dict)
    triggered_by: str = "system"        # "system" | "analyst" | "contract" | "celery"
    tx_hash: str | None = None
    checksum: str = ""                  # SHA-256 of payload (set on write)

    def compute_checksum(self) -> str:
        """SHA-256 fingerprint of the entry (excludes checksum field itself)."""
        payload = {k: v for k, v in asdict(self).items() if k != "checksum"}
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()


# ── Core WORM Writer (ThirdEye Port) ────────────────────────────────
def write_worm_log(event_type: str, details: dict) -> dict:
    """
    Write-Once-Read-Many (WORM) compliant audit log entry.
    Ported directly from ThirdEye audit.py — all entries are append-only.

    Valid ThirdEye event_types: API_INGESTION, EPOCH_ROTATION, THREAT_ALERT
    Third Eye adds:     ANOMALY_DETECTED, SHIELD_ACTIVATED, PSI_MATCH, etc.

    Args:
        event_type: String event identifier (use EventType enum values)
        details:    Arbitrary payload dict to store with the entry

    Returns:
        The written entry dict (including timestamp)
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "event": event_type,
        "payload": details,
        "checksum": hashlib.sha256(
            json.dumps({"event": event_type, "details": details}, sort_keys=True).encode()
        ).hexdigest(),
    }
    WORM_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(WORM_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    logger.info("WORM | %s | %s", event_type, str(details)[:120])
    return entry


# ── High-Level Audit Logger ───────────────────────────────────────
class AuditLogger:
    """
    Structured audit logger for Third Eye detection events.
    Uses write_worm_log() internally for all persistence — guaranteeing
    WORM compliance and backward compatibility with ThirdEye's log format.
    """

    def record(self, event: AuditEvent) -> AuditEvent:
        """
        Persist a structured AuditEvent to the WORM log.
        Computes checksum before writing.
        """
        event.checksum = event.compute_checksum()
        write_worm_log(event.event_type, asdict(event))

        # TODO (Member 3): Mirror to Neo4j
        # await run_query(
        #   "CREATE (e:AuditEvent $props)-[:CONCERNS]->(w:Wallet {address: $addr})",
        #   {"props": asdict(event), "addr": event.wallet_address}
        # )
        return event

    # ── Convenience methods ───────────────────────────────────────

    def log_api_ingestion(self, source: str, record_count: int) -> dict:
        """ThirdEye compat: log a blockchain data ingestion event."""
        return write_worm_log(EventType.API_INGESTION, {
            "source": source,
            "record_count": record_count,
        })

    def log_epoch_rotation(self, model_version: str, epoch: int) -> dict:
        """ThirdEye compat: log an ML model epoch rotation event."""
        return write_worm_log(EventType.EPOCH_ROTATION, {
            "model_version": model_version,
            "epoch": epoch,
        })

    def log_threat_alert(self, wallet: str, risk_score: float, summary: str) -> dict:
        """ThirdEye compat: log a high-severity threat alert."""
        return write_worm_log(EventType.THREAT_ALERT, {
            "wallet_address": wallet,
            "risk_score": risk_score,
            "summary": summary,
        })

    def log_anomaly(self, wallet: str, risk_score: float, hints: list[str]) -> AuditEvent:
        event = AuditEvent(
            event_type=EventType.ANOMALY_DETECTED,
            wallet_address=wallet,
            risk_score=risk_score,
            details={"risk_hints": hints},
        )
        # Also emit a THREAT_ALERT if high severity (ThirdEye compat)
        if risk_score >= 0.75:
            self.log_threat_alert(wallet, risk_score, hints[0] if hints else "High risk detected")
        return self.record(event)

    def log_shield(self, wallet: str, tx_hash: str, triggered_by: str = "system") -> AuditEvent:
        event = AuditEvent(
            event_type=EventType.SHIELD_ACTIVATED,
            wallet_address=wallet,
            triggered_by=triggered_by,
            tx_hash=tx_hash,
        )
        return self.record(event)

    def log_forensic_report(self, wallet: str, report_summary: str) -> AuditEvent:
        event = AuditEvent(
            event_type=EventType.FORENSIC_REPORT,
            wallet_address=wallet,
            details={"summary": report_summary[:500]},
        )
        return self.record(event)

    def log_psi_match(self, wallet: str, matched_signatures: list[str]) -> AuditEvent:
        event = AuditEvent(
            event_type=EventType.PSI_MATCH,
            wallet_address=wallet,
            details={"signatures": matched_signatures},
        )
        return self.record(event)

    def read_log(self, last_n: int = 100) -> list[dict]:
        """
        Read the last N entries from the WORM log (read-only).
        Verifies checksum on each entry — logs a warning if tampered.
        """
        if not WORM_LOG_FILE.exists():
            return []
        entries = []
        with open(WORM_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in lines[-last_n:]:
            try:
                entry = json.loads(line.strip())
                # Verify checksum if present
                stored_checksum = entry.pop("checksum", None)
                if stored_checksum:
                    recomputed = hashlib.sha256(
                        json.dumps(
                            {"event": entry["event"], "details": entry.get("payload", {})},
                            sort_keys=True
                        ).encode()
                    ).hexdigest()
                    if recomputed != stored_checksum:
                        logger.warning("⚠️  Checksum mismatch — log entry may be tampered: %s", line[:80])
                        entry["_tampered"] = True
                    else:
                        entry["checksum"] = stored_checksum
                entries.append(entry)
            except json.JSONDecodeError:
                logger.error("Corrupt log line skipped: %s", line[:80])
        return entries


# ── Module-level singleton ────────────────────────────────────────
audit_logger = AuditLogger()
