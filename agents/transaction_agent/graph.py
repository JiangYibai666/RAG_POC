from __future__ import annotations

import re

from a2a.types import Artifact, DataPart, Message
from tools.pattern_detector import detect_structuring
from tools.transaction_query import find_related_counterparties, find_user_transactions


def _extract_user_id(text: str) -> str:
    m = re.search(r"\bU\d{3,}\b", text.upper())
    return m.group(0) if m else "U000"


def run_transaction_graph(message: Message) -> Artifact:
    query_text = " ".join(part.text for part in message.parts if getattr(part, "type", "") == "text")
    user_id = _extract_user_id(query_text)

    # ── 第二层：交易行为检测 ──────────────────────────────────────────────────

    # 取出该用户的全部历史交易记录，以及涉及其交易对手的关联交易
    txs = find_user_transactions(user_id)
    related = find_related_counterparties(user_id)

    # 检测 B：结构化拆单检测（Structuring）
    # 判断 7 天内是否有 >= 5 笔金额低于 $10,000 的交易（规避监管阈值）
    structuring = detect_structuring(txs)

    # 检测 A：关联方新账户风险
    # 统计交易对手中账户年龄 <= 7 天的笔数；任意 1 笔即触发警报
    new_account_counterparties = len(
        [t for t in txs if float(t.get("counterparty_account_age_days", 999)) <= 7]
    )
    is_structuring = structuring.get("verdict") == "HIGH_RISK_STRUCTURING"

    # TransactionAgent 综合定级：
    # 有新账户对手方 OR 结构化拆单 → HIGH_RISK
    # 历史交易量 >= 10 笔           → MEDIUM_RISK（活跃但无明确警报）
    # 其他                          → LOW_RISK
    if new_account_counterparties > 0 or is_structuring:
        verdict = "HIGH_RISK"
    elif len(txs) >= 10:
        verdict = "MEDIUM_RISK"
    else:
        verdict = "LOW_RISK"

    payload = {
        "user_id": user_id,
        "recent_transaction_count": len(txs),
        "related_counterparty_count": len({t.get("counterparty_id") for t in txs if t.get("counterparty_id")}),
        "new_account_counterparties": new_account_counterparties,
        "structuring": structuring,
        "related_sample_size": len(related),
        "verdict": verdict,
    }

    return Artifact(name="transaction_analysis", parts=[DataPart(data=payload)])
