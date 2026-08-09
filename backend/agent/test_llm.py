from risk_engine import calculate_risk
from llm_engine import generate_report
from audit import log_decision
from psi_engine import mock_psi
import random

# Simulate dynamic transaction
transaction_data = {
    "wallet": f"0x{random.randint(100000,999999)}",
    "tx_count": random.randint(1, 100),
    "cycle_detected": random.choice([True, False]),
    "connected_to_bad_wallet": random.choice([True, False])
}

risk_score, risk_hints = calculate_risk(transaction_data)

report = generate_report(transaction_data["wallet"], risk_score, risk_hints)

print("\n--- AI REPORT ---\n")
print(report)

log_decision(transaction_data["wallet"], risk_score, risk_hints)

# Generate random wallets
def random_wallet():
    return f"0x{random.randint(100000,999999)}"

# Dynamic lists
local_blacklist = [random_wallet() for _ in range(5)]
external_blacklist = [random_wallet() for _ in range(5)]

# Force at least one overlap (important for demo)
external_blacklist.append(local_blacklist[0])

common = mock_psi(local_blacklist, external_blacklist)

print("\nLocal Blacklist:", local_blacklist)
print("External Blacklist:", external_blacklist)
print("Common (PSI):", common)