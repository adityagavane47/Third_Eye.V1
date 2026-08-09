"""
backend/agent/forensic_agent.py — Third Eye Forensic Intelligence Agent

Bridges raw ML/PSI detection signals → Groq-powered AI forensic report.
Called by tasks.py after MLEngine.score() and PSIEngine.match() complete.
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("Third Eye.forensic_agent")


# ── Output Contract ───────────────────────────────────────────────────
@dataclass
class ForensicReport:
    """
    Structured forensic report consumed by:
      - tasks.py  → audit_logger.log_forensic_report(wallet, report.executive_summary)
      - Dashboard → Sidebar panel (risk_level, narrative, actions)
    """
    wallet_address: str
    risk_level: str                          # CRITICAL | HIGH | MEDIUM | LOW
    risk_score: float
    executive_summary: str
    threat_narrative: str
    recommended_actions: list[str] = field(default_factory=list)
    exploit_categories: list[str] = field(default_factory=list)
    signature_matches: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "wallet_address":    self.wallet_address,
            "risk_level":        self.risk_level,
            "risk_score":        self.risk_score,
            "executive_summary": self.executive_summary,
            "threat_narrative":  self.threat_narrative,
            "recommended_actions": self.recommended_actions,
            "exploit_categories": self.exploit_categories,
            "signature_matches": self.signature_matches,
        }


# ── ForensicAgent ─────────────────────────────────────────────────────
class ForensicAgent:
    """
    Orchestrates the final forensic analysis step.

    Flow:
        1. Receives ML risk score + PSI signature matches from tasks.py
        2. Enriches the prompt context with signature descriptions
        3. Calls llm_engine.generate_forensic_report() (Groq / Llama 3.1 8B)
        4. Returns a structured ForensicReport for audit logging and the sidebar
    """

    def __init__(self):
        logger.info("ForensicAgent initialised")

    async def analyze(
        self,
        wallet_address: str,
        risk_score: float,
        confidence: float,
        risk_hints: list[str],
        signature_matches: list[dict],
        label: str = "unknown",
    ) -> ForensicReport:
        """
        Primary async entry point for forensic analysis.

        Args:
            wallet_address:    Target wallet (0x...)
            risk_score:        Composite ML score [0.0, 1.0]
            confidence:        ML model confidence [0.0, 1.0]
            risk_hints:        Human-readable ML risk signals (from MLEngine)
            signature_matches: List of PSI SignatureMatch dicts
                               Each has keys: id, name, description, confidence
            label:             Wallet label from Neo4j (attacker / bot / whale / etc.)

        Returns:
            ForensicReport — structured report ready for sidebar and audit_logger.
        """
        from agent.llm_engine import generate_forensic_report

        # ── Enrich hints with PSI pattern descriptions ────────────────
        # Extract human-readable PSI signals and combine with ML hints
        psi_hints = [
            f"[{m.get('name', 'UNKNOWN').upper()}] {m.get('description', '')} "
            f"(PSI confidence: {m.get('confidence', 0):.0%})"
            for m in signature_matches
        ]
        exploit_categories = list({
            m.get("name", "unknown") for m in signature_matches
        })

        combined_hints = risk_hints + psi_hints

        logger.info(
            "ForensicAgent.analyze(%s) — risk=%.3f, %d ML hints, %d PSI matches",
            wallet_address, risk_score, len(risk_hints), len(signature_matches),
        )

        # ── Call Groq via llm_engine ──────────────────────────────────
        raw = await generate_forensic_report(
            wallet_address=wallet_address,
            risk_score=risk_score,
            label=label,
            risk_hints=combined_hints,
        )

        # ── Map confidence into risk_level ────────────────────────────
        risk_level = raw.get("risk_level") or self._score_to_level(risk_score)

        report = ForensicReport(
            wallet_address=wallet_address,
            risk_level=risk_level,
            risk_score=risk_score,
            executive_summary=raw.get("executive_summary", ""),
            threat_narrative=raw.get("threat_narrative", ""),
            recommended_actions=raw.get("recommended_actions", []),
            exploit_categories=raw.get("exploit_categories", exploit_categories),
            signature_matches=signature_matches,
        )

        logger.info(
            "ForensicReport ready for %s — level=%s, summary='%s'",
            wallet_address, report.risk_level, report.executive_summary[:60],
        )
        return report

    @staticmethod
    def _score_to_level(score: float) -> str:
        if score >= 0.85:
            return "CRITICAL"
        if score >= 0.65:
            return "HIGH"
        if score >= 0.40:
            return "MEDIUM"
        return "LOW"
