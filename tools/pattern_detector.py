from __future__ import annotations

from datetime import datetime, timedelta, timezone


def detect_structuring(transactions: list[dict], threshold: float = 10000.0) -> dict:
    # ── 结构化拆单检测（Structuring Detection）────────────────────────────────
    # 典型洗钱手法：将大额资金拆分为多笔低于监管上报阈值（$10,000）的交易，
    # 以规避 CTR（Currency Transaction Report）等法规要求。

    # 步骤 1：划定 7 天滑动时间窗口，只检查最近 7 天内的交易
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

    # 步骤 2：过滤出金额 < threshold（默认 $10,000）的可疑交易
    suspicious = [tx for tx in in_window if float(tx.get("amount_usd", 0)) < threshold]

    # 步骤 3：若 7 天内可疑笔数 >= 5，判定为高风险结构化交易
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
    # 未达触发条件，返回无结构化信号
    return {
        "pattern_detected": "NONE",
        "evidence": {"transaction_count": len(suspicious), "threshold": threshold, "time_window": "7 days"},
        "verdict": "NO_STRUCTURING_SIGNAL",
    }
