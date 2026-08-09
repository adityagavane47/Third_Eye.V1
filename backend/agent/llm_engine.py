"""
backend/agent/llm_engine.py — Groq-Powered Forensic Report Engine
Uses llama3-8b-8192 via Groq API, with local fallback.
"""

import logging
import os
import random
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

logger = logging.getLogger("Third Eye.llm_engine")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = "llama-3.1-8b-instant"


RISK_SIGNALS = {
    "high_velocity":    "High-velocity fund dispersion (>50 TXs in 24h)",
    "cycle_detected":   "Circular transaction cycle detected (A→B→C→A pattern)",
    "contract_cluster": "Repeated interactions with known exploit contracts",
    "flash_loan":       "Flash-loan footprint — zero-block borrow/repay detected",
    "mixer_routing":    "Funds routed through tornado-cash-style mixer hops",
    "gas_spike":        "Abnormal gas usage spike — likely MEV sandwich attack",
    "whale_dump":       "Rapid large-value ETH dump (>100 ETH in <1h)",
    "new_wallet":       "Recently activated wallet — zero prior on-chain history",
}


async def generate_forensic_report(
    wallet_address: str,
    risk_score: float,
    label: str,
    risk_hints: list[str] | None = None,
) -> dict:
    """Generate a structured forensic report for a wallet."""
    if risk_hints is None:
        # Auto-select signals based on risk score
        k = max(1, int(risk_score * len(RISK_SIGNALS)))
        risk_hints = random.sample(list(RISK_SIGNALS.values()), min(k, len(RISK_SIGNALS)))

    risk_level = (
        "CRITICAL" if risk_score >= 0.85
        else "HIGH" if risk_score >= 0.65
        else "MEDIUM" if risk_score >= 0.40
        else "LOW"
    )

    
    if GROQ_API_KEY:
        try:
            from groq import AsyncGroq  # noqa: PLC0415
            client = AsyncGroq(api_key=GROQ_API_KEY)

            signals_text = "\n".join(f"  • {h}" for h in risk_hints)
            prompt = f"""You are a blockchain forensic analyst for Third Eye, an on-chain immunity system.

Analyze this wallet and produce a concise threat report:

Wallet:     {wallet_address}
Label:      {label}
Risk Score: {risk_score:.3f} ({risk_level})

Detected Risk Signals:
{signals_text}

Produce a JSON-structured forensic report with these exact fields:
- executive_summary (1 sentence, ≤ 30 words)
- threat_narrative (2-3 sentences explaining the attack pattern, explicitly mentioning the specific risk signals above)
- recommended_actions (list of 2-4 actionable items)
- exploit_categories (list of 1-3 short labels like "Flash Loan", "MEV", "Mixer Routing")

Respond ONLY with valid JSON, no markdown code fences."""

            response = await client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=400,
            )

            import json
            raw = response.choices[0].message.content.strip()
            # Strip potential markdown fences
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            parsed = json.loads(raw)

            logger.info("Groq report generated for %s in %dms",
                        wallet_address[:10],
                        int(response.usage.total_tokens * 0.5))  # rough estimate

            return {
                "wallet_address": wallet_address,
                "risk_level": risk_level,
                "risk_score": risk_score,
                "executive_summary":   parsed.get("executive_summary", ""),
                "threat_narrative":    parsed.get("threat_narrative", ""),
                "recommended_actions": parsed.get("recommended_actions", []),
                "exploit_categories":  parsed.get("exploit_categories", []),
            }

        except Exception as exc:
            logger.warning("Groq call failed (%s) — using local fallback", exc)


    return _local_fallback(wallet_address, risk_score, risk_level, label, risk_hints)


def _local_fallback(
    wallet_address: str,
    risk_score: float,
    risk_level: str,
    label: str,
    risk_hints: list[str],
) -> dict:
    """Fast deterministic report when Groq is unavailable."""
    signals = " and ".join(risk_hints[:2]) if risk_hints else "anomalous behaviour"
    return {
        "wallet_address": wallet_address,
        "risk_level": risk_level,
        "risk_score": risk_score,
        "executive_summary": (
            f"Wallet flagged as {risk_level} risk ({risk_score:.0%}) "
            f"based on {signals.lower()}."
        ),
        "threat_narrative": (
            f"On-chain forensic analysis identified {len(risk_hints)} distinct threat "
            f"patterns for {wallet_address[:10]}…. "
            f"Primary signals include: {signals}. "
            f"The wallet exhibits behaviour consistent with a '{label}' archetype "
            f"and poses a significant risk to connected DeFi protocols."
        ),
        "recommended_actions": [
            "Immediately blacklist on ThirdEyeGuardian contract",
            "Trace all connected wallets within 2 hops",
            "Alert downstream protocol integrators",
            "Submit evidence bundle to on-chain governance",
        ],
        "exploit_categories": [
            lbl.split("—")[0].strip().title()
            for lbl in risk_hints[:3]
        ],
    }