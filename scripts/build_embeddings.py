from __future__ import annotations

import json
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).resolve().parent.parent / "mock_data"
KB_PATH = DATA_DIR / "market_knowledge.jsonl"
OUT_PATH = DATA_DIR / "market_embeddings.npy"


def _embed(text: str, dim: int = 128) -> np.ndarray:
    vec = np.zeros(dim, dtype=np.float32)
    for token in text.lower().split():
        vec[hash(token) % dim] += 1.0
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


def main() -> None:
    rows = []
    raw = KB_PATH.read_text(encoding="utf-8").replace("\\n", "\n")
    for line in raw.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))

    embeddings = []
    for row in rows:
        text = f"{row.get('asset_name', '')} {row.get('description', '')}"
        embeddings.append(_embed(text))

    matrix = np.vstack(embeddings) if embeddings else np.zeros((0, 128), dtype=np.float32)
    np.save(OUT_PATH, matrix)
    print(f"Saved embeddings to {OUT_PATH}")


if __name__ == "__main__":
    main()
