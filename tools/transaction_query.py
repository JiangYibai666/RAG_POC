from __future__ import annotations

import json
from pathlib import Path

TRANSACTIONS_PATH = Path(__file__).resolve().parent.parent / "mock_data" / "transactions.json"


def load_transactions() -> list[dict]:
    if not TRANSACTIONS_PATH.exists():
        return []
    return json.loads(TRANSACTIONS_PATH.read_text(encoding="utf-8"))


def find_user_transactions(user_id: str) -> list[dict]:
    return [tx for tx in load_transactions() if tx.get("user_id") == user_id]


def find_related_counterparties(user_id: str) -> list[dict]:
    seen = []
    for tx in find_user_transactions(user_id):
        cp = tx.get("counterparty_id")
        if cp and cp not in seen:
            seen.append(cp)
    return [tx for tx in load_transactions() if tx.get("user_id") in seen or tx.get("counterparty_id") in seen]
