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


def _name_overlap_score(query_tokens: set[str], record: dict) -> float:
    """Fraction of asset-name tokens that appear in the query."""
    name_tokens = set(record.get("asset_name", "").lower().split())
    stopwords = {"the", "a", "an", "and", "of", "in", "for"}
    name_tokens -= stopwords
    if not name_tokens:
        return 0.0
    return len(name_tokens & query_tokens) / len(name_tokens)


def retrieve_market_entries(query: str, top_k: int = 3) -> list[dict]:
    records = _load_kb()
    if not records:
        return []

    embeddings = _load_embeddings(records)
    q = _simple_embed(query, dim=embeddings.shape[1] if embeddings.size else 128)

    if embeddings.size == 0:
        return records[:top_k]

    cosine_scores = embeddings @ q
    query_tokens = set(query.lower().split())
    # Combine name-overlap (primary) with cosine similarity (secondary) so that
    # an exact asset-name match always outranks generic luxury-token similarity.
    combined = [
        (_name_overlap_score(query_tokens, r), float(cosine_scores[i]), i)
        for i, r in enumerate(records)
    ]
    combined.sort(key=lambda t: (t[0], t[1]), reverse=True)

    best_name_score = combined[0][0]

    if best_name_score == 0.0:
        # No name overlap at all — fall back to pure cosine ranking across all records.
        top_idx = np.argsort(cosine_scores)[::-1][:top_k]
        return [records[i] for i in top_idx]

    if best_name_score >= 0.5:
        # Strong name match: return only the single best record so that its price
        # statistics are not diluted by averaging with unrelated assets.
        return [records[combined[0][2]]]

    # Partial name overlap — return top_k by combined score.
    top_idx = [t[2] for t in combined[:top_k]]
    return [records[i] for i in top_idx]
