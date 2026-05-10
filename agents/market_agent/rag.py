from __future__ import annotations

import json
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "mock_data"
KB_PATH = DATA_DIR / "market_knowledge.jsonl"
EMBEDDINGS_PATH = DATA_DIR / "market_embeddings.npy"


def _simple_embed(text: str, dim: int = 128) -> np.ndarray:
    vec = np.zeros(dim, dtype=np.float32)
    for token in text.lower().split():
        idx = hash(token) % dim
        vec[idx] += 1.0
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


def _load_kb() -> list[dict]:
    if not KB_PATH.exists():
        return []
    records = []
    raw = KB_PATH.read_text(encoding="utf-8").replace("\\n", "\n")
    for line in raw.splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def _load_embeddings(records: list[dict]) -> np.ndarray:
    if EMBEDDINGS_PATH.exists():
        cached = np.load(EMBEDDINGS_PATH)
        if cached.shape[0] == len(records):
            return cached
        # Row count mismatch: knowledge base updated but embeddings not rebuilt; regenerate.

    vectors = [_simple_embed((r.get("asset_name", "") + " " + r.get("description", ""))) for r in records]
    if not vectors:
        return np.zeros((0, 128), dtype=np.float32)
    return np.vstack(vectors)


def retrieve_market_entries(query: str, top_k: int = 3) -> list[dict]:
    records = _load_kb()
    if not records:
        return []

    embeddings = _load_embeddings(records)
    q = _simple_embed(query, dim=embeddings.shape[1] if embeddings.size else 128)

    if embeddings.size == 0:
        return records[:top_k]

    scores = embeddings @ q
    top_idx = np.argsort(scores)[::-1][:top_k]
    return [records[i] for i in top_idx]
