"""
backend/core/psi_engine.py — Pattern-Signature Intelligence Engine

Two-layer threat detection:
  Layer 1: PSI (salted SHA-256 private set intersection) — address blacklist matching.
  Layer 2: Structural motif matching — Sandwich Attacks, Bridge Exploits, etc.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("Third Eye.psi_engine")


# ── Exploit Categories ─────────────────────────────────────────────
class ExploitCategory(str, Enum):
    REENTRANCY          = "reentrancy"
    FLASH_LOAN          = "flash_loan"
    PRICE_MANIPULATION  = "price_manipulation"
    SANDWICH_ATTACK     = "sandwich_attack"
    GOVERNANCE_ATTACK   = "governance_attack"
    BRIDGE_EXPLOIT      = "bridge_exploit"
    PSI_ADDRESS_HIT     = "psi_address_hit"
    UNKNOWN             = "unknown"


@dataclass
class SignatureMatch:
    signature_id: str
    category: ExploitCategory
    confidence: float
    matched_addresses: list[str] = field(default_factory=list)
    description: str = ""
    cve_reference: str | None = None


# ── Signature Database ─────────────────────────────────────────────
SIGNATURE_DATABASE: list[dict] = [
    {
        "id": "PSI-001",
        "name": "Classic Reentrancy",
        "category": ExploitCategory.REENTRANCY,
        "pattern": "CALL → balance_check_missing → recursive_CALL",
        "swc": "SWC-107",
        "description": "Contract calls external address before updating internal state",
        "min_reentrancy_depth": 3,
    },
    {
        "id": "PSI-002",
        "name": "Flash Loan Price Oracle Manipulation",
        "category": ExploitCategory.FLASH_LOAN,
        "pattern": "flash_borrow → spot_price_query → swap → repay",
        "description": "Uses flash loan to temporarily distort DEX price oracle",
        "min_gas": 400_000,
        "min_tx_burst": 3,
    },
    {
        "id": "PSI-003",
        "name": "Governance Vote Manipulation",
        "category": ExploitCategory.GOVERNANCE_ATTACK,
        "pattern": "token_accumulation → proposal_creation → instant_vote → execute",
        "description": "Rapid token acquisition to pass malicious governance proposal",
        "min_unique_contracts": 4,
    },
    {
        "id": "PSI-004",
        "name": "Sandwich MEV Attack",
        "category": ExploitCategory.SANDWICH_ATTACK,
        "pattern": "frontrun_tx → victim_tx → backrun_tx",
        "description": "MEV bot sandwiches user transaction for guaranteed profit",
        # Structural: requires at least 3 txs to/from same target in tight sequence
        "min_sandwich_seq": 3,
        "max_time_window_s": 30,
    },
    {
        "id": "PSI-005",
        "name": "Bridge Double-Spend Exploit",
        "category": ExploitCategory.BRIDGE_EXPLOIT,
        "pattern": "deposit → fake_relay → double_withdraw",
        "description": "Cross-chain bridge manipulated — outgoing value far exceeds incoming",
        # Structural: outgoing ETH > incoming ETH by a large factor with few contracts
        "min_outgoing_ratio": 2.0,
        "max_unique_contracts": 3,
        "min_value_eth": 5.0,
    },
]


# ── Layer 1: ThirdEyePSI ─────────────────────────────────────────────
class ThirdEyePSI:
    """
    Simulated Private Set Intersection using salted SHA-256.
    Plaintext addresses are never directly compared — the hash
    acts as a 'ciphertext' that preserves the PSI privacy model.
    """

    SALT = "ThirdEye_PSI_SALT_2026"

    def __init__(self, salt: str = SALT):
        self.salt = salt
        self._encrypted_blacklist: set[str] = set()
        logger.info("ThirdEyePSI initialised (salt prefix: %s…)", salt[:10])

    def _cipher(self, token: str) -> str:
        return hashlib.sha256((self.salt + token.lower()).encode()).hexdigest()

    def encrypt_set(self, tokens: list[str]) -> list[str]:
        return [self._cipher(t) for t in tokens]

    def intersect(self, set_a: list[str], set_b: list[str]) -> list[str]:
        return list(set(set_a).intersection(set_b))

    def load_blacklist(self, known_bad_addresses: list[str]) -> int:
        self._encrypted_blacklist = set(self.encrypt_set(known_bad_addresses))
        logger.info("PSI blacklist loaded: %d addresses", len(self._encrypted_blacklist))
        return len(self._encrypted_blacklist)

    def check_addresses(self, addresses: list[str]) -> list[str]:
        if not self._encrypted_blacklist:
            return []
        ciphered = self.encrypt_set(addresses)
        hit_set = set(self.intersect(ciphered, list(self._encrypted_blacklist)))
        return [addr for addr, c in zip(addresses, ciphered) if c in hit_set]


# ── Layer 2: Structural Motif Extraction ──────────────────────────
def _extract_structural_features(tx_graph: list[dict]) -> dict:
    """
    Extracts structural motifs from a transaction graph, enabling detection
    of Sandwich Attacks, Bridge Exploits, and temporal patterns.
    """
    if not tx_graph:
        return {}

    targets   = [t.get("to", "")        for t in tx_graph]
    gas_vals  = [t.get("gas_used", 21_000) or 21_000 for t in tx_graph]
    eth_vals  = [t.get("value_eth", 0.0) or 0.0 for t in tx_graph]
    timestamps = sorted(
        [t.get("timestamp", 0) for t in tx_graph if t.get("timestamp")],
        key=float,
    )
    incoming_vals = [t.get("incoming_eth", 0.0) or 0.0 for t in tx_graph]

    time_window_s = (
        float(timestamps[-1]) - float(timestamps[0])
        if len(timestamps) >= 2 else 9999.0
    )

    total_outgoing = sum(eth_vals)
    total_incoming = sum(incoming_vals)

    # Sandwich detection: same target hit 3+ times in rapid succession
    target_counts = {t: targets.count(t) for t in set(targets) if t}
    max_target_hit = max(target_counts.values()) if target_counts else 0

    return {
        "tx_count":          len(tx_graph),
        "unique_contracts":  len(set(t for t in targets if t)),
        "max_gas":           max(gas_vals),
        "max_value_eth":     max(eth_vals) if eth_vals else 0.0,
        "total_outgoing":    total_outgoing,
        "total_incoming":    total_incoming,
        "outgoing_ratio":    (total_outgoing / total_incoming) if total_incoming > 0 else 0.0,
        "reentrancy_depth":  max(target_counts.values()) if target_counts else 0,
        "max_target_hit":    max_target_hit,
        "time_window_s":     time_window_s,
    }


# ── Layer 2: Structural Motif Matching ────────────────────────────
def _match_signature(sig: dict, f: dict) -> float:
    """
    Returns confidence score [0, 1] for a signature against extracted features.
    0.0 = no match.
    """
    sid = sig["id"]

    if sid == "PSI-001":  # Reentrancy
        depth = f.get("reentrancy_depth", 0)
        if depth >= sig.get("min_reentrancy_depth", 3):
            return min(0.50 + (depth - 3) * 0.10, 0.95)

    elif sid == "PSI-002":  # Flash loan oracle manipulation
        if (
            f.get("max_gas", 0) >= sig.get("min_gas", 400_000)
            and f.get("tx_count", 0) >= sig.get("min_tx_burst", 3)
        ):
            # Stronger signal if both high gas AND high tx volume
            confidence = 0.70 + 0.10 * min(f["tx_count"] / 10, 1.0)
            return round(confidence, 2)

    elif sid == "PSI-003":  # Governance attack
        if f.get("unique_contracts", 0) >= sig.get("min_unique_contracts", 4):
            return min(0.55 + f["unique_contracts"] * 0.02, 0.85)

    elif sid == "PSI-004":  # Sandwich MEV — structural motif
        # Requires: same target hit repeatedly AND txs within a tight time window
        if (
            f.get("max_target_hit", 0) >= sig.get("min_sandwich_seq", 3)
            and f.get("time_window_s", 9999) <= sig.get("max_time_window_s", 30)
        ):
            return min(0.70 + f["max_target_hit"] * 0.05, 0.95)

    elif sid == "PSI-005":  # Bridge exploit — structural motif
        # Outgoing ETH significantly exceeds incoming with minimal contracts involved
        if (
            f.get("outgoing_ratio", 0.0) >= sig.get("min_outgoing_ratio", 2.0)
            and f.get("unique_contracts", 999) <= sig.get("max_unique_contracts", 3)
            and f.get("total_outgoing", 0.0) >= sig.get("min_value_eth", 5.0)
        ):
            ratio = f["outgoing_ratio"]
            return min(0.60 + (ratio - 2.0) * 0.08, 0.92)

    return 0.0


# ── Unified PSIEngine ──────────────────────────────────────────────
class PSIEngine:
    """
    Third Eye Pattern-Signature Intelligence Engine.

    Layer 1: ThirdEyePSI — salted SHA-256 address blacklist matching.
    Layer 2: Structural motif matching (Sandwich, Bridge, Reentrancy, etc.)
    """

    def __init__(self):
        self.psi = ThirdEyePSI()
        self.signatures = SIGNATURE_DATABASE
        logger.info(
            "PSIEngine initialised — %d signatures loaded",
            len(self.signatures),
        )

    def load_blacklist(self, known_bad_addresses: list[str]) -> int:
        return self.psi.load_blacklist(known_bad_addresses)

    def match(
        self,
        wallet_address: str,
        tx_graph: list[dict],
        related_addresses: list[str] | None = None,
    ) -> list[SignatureMatch]:
        """
        Full two-layer scan.

        Args:
            wallet_address:     Target wallet (0x...)
            tx_graph:           List of tx edge dicts from Neo4j
            related_addresses:  Additional counterparty addresses to PSI-check

        Returns:
            List of SignatureMatch objects, sorted by confidence descending.
        """
        matches: list[SignatureMatch] = []

        # ── Layer 1: PSI blacklist check ─────────────────────────
        all_addresses = [wallet_address] + (related_addresses or [])
        psi_hits = self.psi.check_addresses(all_addresses)
        if psi_hits:
            matches.append(SignatureMatch(
                signature_id="PSI-000",
                category=ExploitCategory.PSI_ADDRESS_HIT,
                confidence=0.95,
                matched_addresses=psi_hits,
                description=f"Address matched Third Eye blacklist via PSI: {psi_hits}",
            ))
            logger.warning(
                "PSI hit for %s — %d blacklisted address(es)",
                wallet_address, len(psi_hits),
            )

        # ── Layer 2: Structural motif matching ───────────────────
        if not tx_graph:
            logger.debug("PSIEngine.match(%s) — empty tx_graph, skipping pattern check", wallet_address)
            return matches

        features = _extract_structural_features(tx_graph)

        for sig in self.signatures:
            confidence = _match_signature(sig, features)
            if confidence > 0.0:
                matches.append(SignatureMatch(
                    signature_id=sig["id"],
                    category=sig["category"],
                    confidence=confidence,
                    matched_addresses=[wallet_address],
                    description=sig["description"],
                    cve_reference=sig.get("swc"),
                ))
                logger.info(
                    "Signature match: %s [%s] conf=%.2f for %s",
                    sig["id"], sig["name"], confidence, wallet_address,
                )

        matches.sort(key=lambda m: m.confidence, reverse=True)
        return matches

    def get_signature_by_id(self, sig_id: str) -> dict | None:
        return next((s for s in self.signatures if s["id"] == sig_id), None)


# ── Module-level singleton ────────────────────────────────────────
psi_service = ThirdEyePSI()
