from __future__ import annotations

from datetime import datetime, timedelta, timezone


def detect_structuring(transactions: list[dict], threshold: float = 10000.0) -> dict:
    now = datetime.now(timezone.utc)
    window = now - timedelta(days=7)
    in_window = []
    for tx in transactions:
        try:
            ts = datetime.fromisoformat(tx["timestamp"].replace("Z", "+00:00"))
        except Exception:
            continue
        if ts >= window:
            in_window.append(tx)

    suspicious = [tx for tx in in_window if float(tx.get("amount_usd", 0)) < threshold]
    if len(suspicious) >= 5:
        amounts = [float(tx.get("amount_usd", 0)) for tx in suspicious]
        return {
            "pattern_detected": "STRUCTURING",
            "evidence": {
                "transaction_count": len(suspicious),
                "amount_range": [min(amounts), max(amounts)],
                "threshold": threshold,
                "time_window": "7 days",
            },
            "verdict": "HIGH_RISK_STRUCTURING",
        }
    return {
        "pattern_detected": "NONE",
        "evidence": {"transaction_count": len(suspicious), "threshold": threshold, "time_window": "7 days"},
        "verdict": "NO_STRUCTURING_SIGNAL",
    }
