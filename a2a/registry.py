from __future__ import annotations

import os


AGENT_ENDPOINTS = {
    "HostAgent": os.getenv("HOST_AGENT_URL", "http://127.0.0.1:10000"),
    "MarketAgent": os.getenv("MARKET_AGENT_URL", "http://127.0.0.1:10001"),
    "TransactionAgent": os.getenv("TRANSACTION_AGENT_URL", "http://127.0.0.1:10002"),
}
