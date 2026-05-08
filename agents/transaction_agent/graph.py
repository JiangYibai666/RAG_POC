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

    txs = find_user_transactions(user_id)
    related = find_related_counterparties(user_id)
    structuring = detect_structuring(txs)

    payload = {
        "user_id": user_id,
        "recent_transaction_count": len(txs),
        "related_counterparty_count": len({t.get("counterparty_id") for t in txs if t.get("counterparty_id")}),
        "new_account_counterparties": len(
            [t for t in txs if float(t.get("counterparty_account_age_days", 999)) <= 7]
        ),
        "structuring": structuring,
        "related_sample_size": len(related),
        "verdict": "HIGH_RISK" if len(txs) >= 3 or structuring.get("verdict") == "HIGH_RISK_STRUCTURING" else "MEDIUM_RISK",
    }

    return Artifact(name="transaction_analysis", parts=[DataPart(data=payload)])
