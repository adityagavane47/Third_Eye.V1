"""
backend/test_engines.py — Quick verification that ML + PSI engines are working.
Run from the backend directory:
    python test_engines.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")


async def main():
    from core.ml_engine import MLEngine, WEIGHTS_PATH
    from core.psi_engine import PSIEngine

    print("\n" + "="*60)
    print("  Third Eye — ENGINE VERIFICATION")
    print("="*60)

    # ── 1. Check model weights ───────────────────────────────
    if WEIGHTS_PATH.exists():
        size_kb = WEIGHTS_PATH.stat().st_size // 1024
        print(f"\n[ML]  Trained weights found: isolation_forest.pkl ({size_kb} KB)")
    else:
        print("\n[ML]  WARNING: No trained weights found. Run scripts/train_ml.py first.")

    # ── 2. Score a simulated NORMAL wallet ──────────────────
    ml = MLEngine()
    normal_tx = [{"to": "0xabc", "value_eth": 0.5, "gas_used": 21000} for _ in range(5)]
    normal_result = await ml.score("0xNORMAL_WALLET", normal_tx)
    print(f"\n[ML]  Normal wallet score:   {normal_result.score:.4f}  (expect < 0.5)")
    print(f"      Confidence:             {normal_result.confidence:.4f}")
    print(f"      Risk hints:             {normal_result.risk_hints}")

    # ── 3. Score a simulated ATTACKER wallet ────────────────
    attacker_tx = (
        [{"to": "0xDEAD", "value_eth": 80.0, "gas_used": 550_000}] * 15
        + [{"to": "0xDEAD", "value_eth": 50.0, "gas_used": 21_000}] * 120
    )
    attack_result = await ml.score("0xATTACKER_WALLET", attacker_tx)
    print(f"\n[ML]  Attacker wallet score: {attack_result.score:.4f}  (expect > 0.5)")
    print(f"      Confidence:             {attack_result.confidence:.4f}")
    print(f"      Risk hints:             {attack_result.risk_hints}")
    print(f"      Top contributors:       {attack_result.top_contributors}")

    # ── 4. PSI sandwich attack detection ────────────────────
    psi = PSIEngine()
    sandwich_txs = [
        {"to": "0xUNISWAP", "value_eth": 5.0, "gas_used": 21_000, "timestamp": 1000},
        {"to": "0xUNISWAP", "value_eth": 5.0, "gas_used": 21_000, "timestamp": 1010},
        {"to": "0xUNISWAP", "value_eth": 5.0, "gas_used": 21_000, "timestamp": 1020},
    ]
    matches = psi.match("0xMEVBOT", sandwich_txs)
    print(f"\n[PSI] Sandwich attack test:")
    if matches:
        for m in matches:
            print(f"      MATCH: {m.signature_id} [{m.category.value}] conf={m.confidence:.0%}")
            print(f"             {m.description}")
    else:
        print("      No patterns matched.")

    # ── 5. PSI bridge exploit detection ─────────────────────
    bridge_txs = [
        {"to": "0xBRIDGE", "value_eth": 50.0, "gas_used": 21_000, "incoming_eth": 10.0},
        {"to": "0xBRIDGE", "value_eth": 50.0, "gas_used": 21_000, "incoming_eth": 5.0},
    ]
    bridge_matches = psi.match("0xBRIDGEEXPLOITER", bridge_txs)
    print(f"\n[PSI] Bridge exploit test:")
    if bridge_matches:
        for m in bridge_matches:
            print(f"      MATCH: {m.signature_id} [{m.category.value}] conf={m.confidence:.0%}")
    else:
        print("      No patterns matched.")

    # ── 6. PSI blacklist check ───────────────────────────────
    psi.load_blacklist(["0xBADADDRESS1", "0xBADADDRESS2"])
    hits = psi.psi.check_addresses(["0xBADADDRESS1", "0xCLEAN"])
    print(f"\n[PSI] Blacklist check:  hits={hits}  (expect ['0xBADADDRESS1'])")

    print("\n" + "="*60)
    print("  ALL CHECKS COMPLETE")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
