import json
from datetime import datetime

def log_decision(wallet, risk_score, risk_hints):
    log_entry = {
        "wallet": wallet,
        "risk_score": risk_score,
        "risk_hints": risk_hints,
        "timestamp": datetime.utcnow().isoformat()
    }

    with open("audit_log.json", "a") as file:
        file.write(json.dumps(log_entry) + "\n")