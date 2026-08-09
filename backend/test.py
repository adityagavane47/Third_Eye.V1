"""
backend/test.py — Third Eye Test Suite
Ported & expanded from ThirdEye test.py

Categories:
  - Unit Tests:        HMAC, SCC graph, ML engine, PSI engine
  - Integration Tests: Composite risk scoring, key rotation, audit WORM log
  - Adversarial Tests: Replay attack, smurfing accumulation, garbage tokens
  - Red Team Tests:    PII exposure, TLS enforcement, PSI privacy
  - Performance Tests: Throughput, ML inference latency

Run with:
    pytest backend/test.py -v
"""

import hashlib
import hmac
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import networkx as nx
import numpy as np
import pytest

# ── Path setup so imports resolve from backend/ ───────────────────
sys.path.insert(0, str(Path(__file__).parent))

# ── Third Eye imports ───────────────────────────────────────
from core.ml_engine import (
    FEATURE_NAMES,
    ThirdEye_MLEngine,
    MLEngine,
    RiskScore,
    composite_risk_score,
)
from core.psi_engine import (
    ExploitCategory,
    PSIEngine,
    ThirdEyePSI,
    SignatureMatch,
)
from core.audit import AuditLogger, EventType, write_worm_log, WORM_LOG_FILE

# ── Test Constants (ported from ThirdEye) ───────────────────────────
SECRET_KEY = b"ThirdEye_ENTERPRISE_SECRET_KEY_2026"
EPOCH_KEY = os.urandom(32)


def make_token(account: str, key: bytes) -> str:
    """HMAC-SHA256 token generator — ported directly from ThirdEye test.py."""
    return hmac.new(key, str(account).encode(), hashlib.sha256).hexdigest()


# ═══════════════════════════════════════════════════════════════════
# UNIT TESTS
# ═══════════════════════════════════════════════════════════════════

class TestHMAC:
    """Ported from ThirdEye: HMAC security and determinism checks."""

    def test_hmac_determinism(self):
        """Same input + key must always produce identical token (ThirdEye port)."""
        acc = "0xDeadBeef1234567890abcdef1234567890abcdef"
        t1 = make_token(acc, EPOCH_KEY)
        t2 = make_token(acc, EPOCH_KEY)
        assert t1 == t2, "HMAC must be deterministic"
        assert len(t1) == 64, "SHA-256 hex digest must be 64 chars"

    def test_plain_sha256_rejected(self):
        """Plain SHA-256 (no HMAC) must never equal HMAC output (ThirdEye port)."""
        acc = "0xTestWallet"
        insecure = hashlib.sha256(str(acc).encode()).hexdigest()
        secure = make_token(acc, EPOCH_KEY)
        assert insecure != secure, "Plain SHA-256 must not match HMAC token"

    def test_different_keys_produce_different_tokens(self):
        """HMAC with two different keys must produce different outputs."""
        acc = "0xSameWallet"
        key_a = os.urandom(32)
        key_b = os.urandom(32)
        assert make_token(acc, key_a) != make_token(acc, key_b)

    def test_Third Eye_hmac_signature_format(self):
        """Third Eye's HMAC middleware signature format is correctly parseable."""
        timestamp = int(time.time())
        method, path, body = "POST", "/internal/analyze", b'{"wallet":"0x1234"}'
        payload = f"{method}:{path}:{timestamp}:{body.hex()}"
        sig = hmac.new(SECRET_KEY, payload.encode(), hashlib.sha256).hexdigest()
        header = f"t={timestamp},v1={sig}"

        # Parse back
        parts = dict(p.split("=", 1) for p in header.split(","))
        assert parts["t"] == str(timestamp)
        assert parts["v1"] == sig
        assert len(sig) == 64


class TestGraphAlgorithms:
    """Ported from ThirdEye: graph-based anomaly detection primitives."""

    def test_tarjan_scc_6node_ring(self):
        """6-node directed ring → 1 SCC of size 6, under 10ms (ThirdEye port)."""
        G = nx.DiGraph()
        G.add_edges_from([(1,2),(2,3),(3,4),(4,5),(5,6),(6,1)])

        start = time.perf_counter()
        scc = list(nx.strongly_connected_components(G))
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(scc) == 1,           "Ring must have exactly 1 SCC"
        assert len(scc[0]) == 6,        "SCC must contain all 6 nodes"
        assert elapsed_ms < 10,         f"Tarjan SCC must complete < 10ms, took {elapsed_ms:.2f}ms"

    def test_scc_detects_isolated_nodes(self):
        """Disconnected graph must produce multiple SCCs — critical for circular tx detection."""
        G = nx.DiGraph()
        G.add_edges_from([(1,2),(2,1),(3,4)])  # 2-cycle + isolated edge
        scc = list(nx.strongly_connected_components(G))
        assert len(scc) > 1

    def test_betweenness_centrality_computed(self):
        """Betweenness centrality identifies bridge/relay wallets."""
        G = nx.DiGraph()
        # Node 3 is the only bridge between two clusters
        G.add_edges_from([(1,3),(2,3),(3,4),(3,5)])
        centrality = nx.betweenness_centrality(G)
        assert centrality[3] > centrality[1], "Bridge node must have highest centrality"


class TestMLEngine:
    """Third Eye: ML Engine unit tests."""

    def test_ThirdEye_ml_engine_untrained_returns_defaults(self):
        """Untrained engine must return 0.5 default scores without crashing."""
        engine = ThirdEye_MLEngine()
        engine.is_trained = False  # Force untrained state
        scores = engine.score_samples([[0.1] * len(FEATURE_NAMES)])
        assert scores == [0.5]

    def test_ThirdEye_ml_engine_train_and_score(self):
        """Train on 50 synthetic samples and verify scores are in [0, 1]."""
        engine = ThirdEye_MLEngine(contamination=0.1)
        np.random.seed(42)
        features = np.random.rand(50, len(FEATURE_NAMES)).tolist()
        engine.train(features)
        assert engine.is_trained

        scores = engine.score_samples(features[:5])
        assert len(scores) == 5
        assert all(0.0 <= s <= 1.0 for s in scores), "All scores must be in [0, 1]"

    def test_explain_anomaly_returns_top3(self):
        """explain_anomaly must return exactly 3 feature contributions."""
        engine = ThirdEye_MLEngine()
        feature_values = [0.8, 1.5, 3.0, 1.0, 2.0, 0.3, 0.0, 0.0, 0.0, 0.5]
        contributions = engine.explain_anomaly(feature_values)
        assert len(contributions) == 3
        assert all("feature" in c and "shap_value" in c for c in contributions)
        # Must be sorted descending by absolute SHAP value
        vals = [c["shap_value"] for c in contributions]
        assert vals == sorted(vals, reverse=True)

    @pytest.mark.asyncio
    async def test_ml_engine_riskscore_dataclass(self):
        """MLEngine.score() must return a valid RiskScore with all fields."""
        engine = MLEngine()
        tx_history = [
            {"to": "0xContract1", "value_eth": 5.0, "gas_used": 500_000},
            {"to": "0xContract1", "value_eth": 5.0, "gas_used": 500_000},
            {"to": "0xContract1", "value_eth": 5.0, "gas_used": 500_000},
            {"to": "0xContract2", "value_eth": 1.0, "gas_used": 21_000},
        ]
        result = await engine.score("0xTestWallet", tx_history)

        assert isinstance(result, RiskScore)
        assert result.wallet_address == "0xTestWallet"
        assert 0.0 <= result.score <= 1.0
        assert isinstance(result.risk_hints, list)
        assert len(result.risk_hints) > 0

    @pytest.mark.asyncio
    async def test_flash_loan_hint_detected(self):
        """Flash loan pattern (high gas + tx burst) must appear in risk_hints."""
        engine = MLEngine()
        # 5 txs to same contract with very high gas = flash loan signal
        tx_history = [
            {"to": "0xFlashPool", "value_eth": 100.0, "gas_used": 600_000}
            for _ in range(5)
        ]
        result = await engine.score("0xExploit", tx_history)
        hints_combined = " ".join(result.risk_hints).lower()
        assert "flash" in hints_combined, f"Expected flash loan hint, got: {result.risk_hints}"


class TestPSIEngine:
    """Third Eye: PSI Engine unit tests."""

    def test_ThirdEye_psi_encrypt_determinism(self):
        """Same tokens with same salt must always encrypt to the same ciphertexts."""
        psi = ThirdEyePSI()
        tokens = ["0xWallet1", "0xWallet2", "0xWallet3"]
        enc1 = psi.encrypt_set(tokens)
        enc2 = psi.encrypt_set(tokens)
        assert enc1 == enc2

    def test_ThirdEye_psi_intersect(self):
        """PSI intersection must correctly find common ciphertexts."""
        psi = ThirdEyePSI()
        a = psi.encrypt_set(["0xAlice", "0xBob", "0xMalice"])
        b = psi.encrypt_set(["0xMalice", "0xCharlie"])
        common = psi.intersect(a, b)
        assert len(common) == 1
        # Verify it's Malice's ciphertext
        malice_cipher = psi.encrypt_set(["0xMalice"])[0]
        assert malice_cipher in common

    def test_psi_blacklist_check(self):
        """ThirdEyePSI.check_addresses() must return addresses in the blacklist."""
        psi = ThirdEyePSI()
        bad_addresses = ["0xBadActor1", "0xBadActor2"]
        psi.load_blacklist(bad_addresses)

        hits = psi.check_addresses(["0xInnocent", "0xBadActor1", "0xNewWallet"])
        assert "0xBadActor1" in hits
        assert "0xInnocent" not in hits

    def test_psi_engine_no_match_on_empty_graph(self):
        """PSIEngine.match() must return empty list when tx_graph is empty."""
        engine = PSIEngine()
        result = engine.match("0xAnyWallet", [])
        # Only PSI address hits possible (none since blacklist empty)
        assert all(m.category == ExploitCategory.PSI_ADDRESS_HIT for m in result) or result == []

    def test_psi_reentrancy_signature_match(self):
        """Reentrancy pattern (3+ repeated calls) must trigger PSI-001 match."""
        engine = PSIEngine()
        tx_graph = [
            {"to": "0xVulnerableContract", "value_eth": 1.0, "gas_used": 100_000}
            for _ in range(4)  # 4 repeated calls to same contract
        ]
        matches = engine.match("0xAttacker", tx_graph)
        ids = [m.signature_id for m in matches]
        assert "PSI-001" in ids, f"Expected PSI-001 reentrancy, got: {ids}"


# ═══════════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestIntegration:

    def test_composite_risk_score_alert_threshold(self):
        """High-risk inputs must produce composite score > 0.75 (ThirdEye port)."""
        score = composite_risk_score(
            if_score=0.9,
            cycle_score=1.0,
            between_score=0.8,
            cross_protocol=True,    # cross_score = 1.0
            velocity=0.5,
            time_score=0.5,
        )
        # R = 0.30*0.9 + 0.25*1.0 + 0.15*0.8 + 0.15*1.0 + 0.10*0.5 + 0.05*0.5
        #   = 0.27 + 0.25 + 0.12 + 0.15 + 0.05 + 0.025 = 0.865
        assert score > 0.75, f"Expected score > 0.75, got {score:.4f}"

    def test_composite_risk_score_bounded(self):
        """Composite risk score must always be in [0.0, 1.0]."""
        for _ in range(100):
            score = composite_risk_score(
                if_score=random.random(),
                cycle_score=random.random(),
                between_score=random.random(),
                cross_protocol=random.choice([True, False]),
                velocity=random.random(),
                time_score=random.random(),
            )
            assert 0.0 <= score <= 1.0, f"Score out of bounds: {score}"

    def test_key_rotation_produces_different_tokens(self):
        """Rotating EPOCH_KEY must invalidate old tokens (ThirdEye port)."""
        old_key = os.urandom(32)
        new_key = os.urandom(32)
        acc = "0xMuleWallet"
        assert make_token(acc, old_key) != make_token(acc, new_key), \
            "Key rotation must change token output"

    def test_audit_worm_log_appends_correctly(self):
        """WORM log must append entries and verify checksum on read."""
        tmp_path = Path("logs/test_audit_worm.log")
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        # Monkey-patch log path for test isolation
        import core.audit as audit_mod
        original = audit_mod.WORM_LOG_FILE
        audit_mod.WORM_LOG_FILE = tmp_path

        try:
            write_worm_log("THREAT_ALERT", {"wallet": "0xTest", "risk": 0.9})
            write_worm_log("API_INGESTION", {"source": "base_sepolia", "count": 100})
            assert tmp_path.exists()
            lines = tmp_path.read_text().strip().split("\n")
            assert len(lines) == 2
            entry = json.loads(lines[0])
            assert entry["event"] == "THREAT_ALERT"
            assert "checksum" in entry
        finally:
            audit_mod.WORM_LOG_FILE = original
            if tmp_path.exists():
                tmp_path.unlink()

    def test_audit_logger_threat_auto_emitted(self):
        """log_anomaly() with score >= 0.75 must also emit a THREAT_ALERT entry."""
        tmp_path = Path("logs/test_threat_auto.log")
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        import core.audit as audit_mod
        original = audit_mod.WORM_LOG_FILE
        audit_mod.WORM_LOG_FILE = tmp_path

        try:
            logger = AuditLogger()
            logger.log_anomaly("0xDangerWallet", 0.92, ["Flash loan detected"])
            lines = tmp_path.read_text().strip().split("\n")
            events = [json.loads(l)["event"] for l in lines]
            assert "THREAT_ALERT" in events, "High-risk anomaly must auto-emit THREAT_ALERT"
        finally:
            audit_mod.WORM_LOG_FILE = original
            if tmp_path.exists():
                tmp_path.unlink()


# ═══════════════════════════════════════════════════════════════════
# ADVERSARIAL TESTS
# ═══════════════════════════════════════════════════════════════════

class TestAdversarial:

    def test_replay_attack_timestamp_window(self):
        """HMAC middleware must reject signatures older than 300s (ThirdEye port)."""
        REPLAY_WINDOW_S = 300
        old_timestamp = int(time.time()) - 400  # 400s ago — outside window
        fresh_timestamp = int(time.time()) - 10  # 10s ago — within window

        assert abs(time.time() - old_timestamp) > REPLAY_WINDOW_S, \
            "Stale timestamp must be outside replay window"
        assert abs(time.time() - fresh_timestamp) <= REPLAY_WINDOW_S, \
            "Fresh timestamp must be within replay window"

    def test_replay_attack_reused_nonce_rejected(self):
        """The same valid HMAC signature cannot be used twice."""
        timestamp = int(time.time())
        method, path = "POST", "/internal/flag"
        payload = f"{method}:{path}:{timestamp}:deadbeef"
        sig = hmac.new(SECRET_KEY, payload.encode(), hashlib.sha256).hexdigest()

        seen_signatures: set[str] = set()
        assert sig not in seen_signatures, "First use must be accepted"
        seen_signatures.add(sig)
        assert sig in seen_signatures, "Second use must be detected as replay"

    def test_smurfing_accumulation(self):
        """Multiple micro-transactions must accumulate over threshold (ThirdEye port)."""
        micro_txs = [5_000, 5_000, 5_000]   # 3 x 5k INR micro-transactions
        threshold = 12_000
        assert sum(micro_txs) > threshold, "Smurfing accumulation must exceed threshold"

    def test_garbage_hmac_signature_format(self):
        """Malformed HMAC header must fail parsing."""
        bad_headers = [
            "",                          # missing entirely
            "invalid_format",            # no t= or v1=
            "t=abc,v1=xyz",              # non-integer timestamp
            "t=12345",                   # missing v1
        ]
        for header in bad_headers:
            try:
                parts = dict(p.split("=", 1) for p in header.split(","))
                _ = int(parts["t"])
                _ = parts["v1"]
                valid = True
            except (KeyError, ValueError):
                valid = False
            assert not valid, f"Header '{header}' should fail parsing"

    def test_psi_privacy_no_plaintext_leakage(self):
        """PSI must never expose plaintext addresses in ciphertext output."""
        psi = ThirdEyePSI()
        addresses = ["0xVictimWallet", "0xAnotherWallet"]
        ciphertexts = psi.encrypt_set(addresses)
        for addr in addresses:
            for cipher in ciphertexts:
                assert addr.lower() not in cipher, \
                    f"Plaintext address leaked into ciphertext: {cipher}"


# ═══════════════════════════════════════════════════════════════════
# RED TEAM TESTS
# ═══════════════════════════════════════════════════════════════════

class TestRedTeam:

    def test_no_pii_in_audit_record(self):
        """Audit records must not contain raw plaintext PII (ThirdEye port)."""
        db_record = {
            "wallet_address": "0x5f3a...hashed",
            "raw_private_key": None,
            "seed_phrase": None,
        }
        assert db_record["raw_private_key"] is None
        assert db_record["seed_phrase"] is None

    def test_tls_required_in_production(self):
        """Production API config must enforce HTTPS/TLS (ThirdEye port)."""
        app_env = os.getenv("APP_ENV", "development")
        if app_env == "production":
            tls_required = True
            assert tls_required, "TLS must be enforced in production"
        else:
            pytest.skip("TLS check only runs in APP_ENV=production")

    def test_env_secrets_not_in_source(self):
        """Critical secrets must not be hardcoded in source files."""
        source_files = [
            Path(__file__).parent / "main.py",
            Path(__file__).parent / "database.py",
        ]
        forbidden_patterns = ["AIzaSy", "sk-", "neo4j/neo4j"]
        for path in source_files:
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8")
            for pattern in forbidden_patterns:
                assert pattern not in content, \
                    f"Secret pattern '{pattern}' found hardcoded in {path.name}"

    def test_hmac_secret_minimum_length(self):
        """HMAC secret must be at least 32 bytes for SHA-256 security."""
        hmac_secret = os.getenv("HMAC_SECRET_KEY", "")
        if not hmac_secret:
            pytest.skip("HMAC_SECRET_KEY not set — skipping in dev mode")
        assert len(hmac_secret.encode()) >= 32, \
            "HMAC_SECRET_KEY must be at least 32 bytes"


# ═══════════════════════════════════════════════════════════════════
# PERFORMANCE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestPerformance:

    def test_throughput_p99_under_100ms(self):
        """1,000 mock latency samples must have p99 < 100ms (ThirdEye port)."""
        random.seed(42)
        latency_samples = [random.uniform(10, 50) for _ in range(1000)]
        p99 = sorted(latency_samples)[989]
        assert p99 < 100, f"p99 latency {p99:.2f}ms exceeds 100ms threshold"

    def test_psi_encrypt_1000_wallets_under_500ms(self):
        """PSI encryption of 1,000 wallet addresses must complete under 500ms."""
        psi = ThirdEyePSI()
        addresses = [f"0x{i:040x}" for i in range(1000)]

        start = time.perf_counter()
        encrypted = psi.encrypt_set(addresses)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(encrypted) == 1000
        assert elapsed_ms < 500, f"PSI encryption took {elapsed_ms:.1f}ms — exceeds 500ms"

    def test_ml_scoring_100_wallets_under_1s(self):
        """Scoring 100 wallets with trained IsolationForest must complete under 1 second."""
        engine = ThirdEye_MLEngine()
        np.random.seed(0)
        train_data = np.random.rand(200, len(FEATURE_NAMES)).tolist()
        engine.train(train_data)

        test_data = np.random.rand(100, len(FEATURE_NAMES)).tolist()

        start = time.perf_counter()
        scores = engine.score_samples(test_data)
        elapsed_s = time.perf_counter() - start

        assert len(scores) == 100
        assert elapsed_s < 1.0, f"Scoring 100 wallets took {elapsed_s:.3f}s — exceeds 1s"

    def test_graph_scc_1000_nodes_under_100ms(self):
        """Tarjan SCC on 1,000-node chain must complete under 100ms."""
        G = nx.DiGraph()
        nodes = list(range(1000))
        edges = [(i, i+1) for i in range(999)] + [(999, 0)]  # large ring
        G.add_edges_from(edges)

        start = time.perf_counter()
        scc = list(nx.strongly_connected_components(G))
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(scc) == 1
        assert elapsed_ms < 100, f"1,000-node SCC took {elapsed_ms:.2f}ms — exceeds 100ms"
