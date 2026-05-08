from __future__ import annotations

from agents.market_agent.rag import retrieve_market_entries


def lookup_asset_market(asset_query: str, top_k: int = 3) -> list[dict]:
    return retrieve_market_entries(asset_query, top_k=top_k)
