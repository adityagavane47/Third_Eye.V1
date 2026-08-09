def calculate_risk(transaction_data):
    risk_score = 0
    risk_hints = []


    if transaction_data.get("tx_count", 0) > 20:
        risk_score += 0.4
        risk_hints.append("High transaction velocity detected")

    if transaction_data.get("cycle_detected", False):
        risk_score += 0.3
        risk_hints.append("Part of cyclic fund movement")

    if transaction_data.get("connected_to_bad_wallet", False):
        risk_score += 0.3
        risk_hints.append("Connected to known malicious wallet")


    risk_score = min(risk_score, 1.0)

    return risk_score, risk_hints