from __future__ import annotations

import re
from statistics import mean

from a2a.types import Artifact, DataPart, Message
from tools.market_search import lookup_asset_market


def _extract_price(text: str) -> float:
    cleaned = text.replace(",", "").replace("$", " $")
    matches = re.findall(r"\$?\s*([0-9]+(?:\.[0-9]+)?)", cleaned)
    if not matches:
        return 0.0
    return max(float(m) for m in matches)


def run_market_graph(message: Message) -> Artifact:
    query_text = " ".join(part.text for part in message.parts if getattr(part, "type", "") == "text")
    # ── 第一层：价格异常检测（Z-score）────────────────────────────────────────

    # 步骤 1：从用户输入中抽取交易价格（正则匹配最大数字）
    price = _extract_price(query_text)

    # 步骤 2：通过 RAG 检索出最相关的 1~3 条市场记录
    # lookup_asset_market 先做名称重叠评分，再做余弦相似度，强名称匹配只返回 1 条
    entries = lookup_asset_market(query_text, top_k=3)

    if not entries:
        payload = {
            "asset": "unknown",
            "fair_range": {"min": 0, "max": 0},
            "historical_mean": 0,
            "historical_stddev": 0,
            "queried_price": price,
            "deviation_sigma": 0,
            "verdict": "INSUFFICIENT_DATA",
        }
        return Artifact(name="market_analysis", parts=[DataPart(data=payload)])

    mins = [float(e["price_range"]["min"]) for e in entries]
    maxs = [float(e["price_range"]["max"]) for e in entries]
    means = [float(e["historical_mean"]) for e in entries]
    stds = [max(float(e["historical_stddev"]), 1.0) for e in entries]

    # 步骤 3：对检索到的多条记录取均值，得到市场参考均值 μ 和标准差 σ
    mu = mean(means)
    sigma = mean(stds)

    # 步骤 4：计算实际价格偏离 μ 多少个标准差（即 Z-score）
    # deviation_sigma = |queried_price - μ| / σ
    deviation_sigma = abs(price - mu) / sigma if sigma > 0 else 0.0

    # 根据 Z-score 判定价格异常等级：
    # >= 5σ → 极端异常（EXTREMELY_ANOMALOUS）
    # >= 3σ → 高度异常（HIGHLY_ANOMALOUS）
    # >= 2σ → 中度异常（MODERATELY_ANOMALOUS）
    # <  2σ → 正常区间（WITHIN_NORMAL_RANGE）
    if deviation_sigma >= 5:
        verdict = "EXTREMELY_ANOMALOUS"
    elif deviation_sigma >= 3:
        verdict = "HIGHLY_ANOMALOUS"
    elif deviation_sigma >= 2:
        verdict = "MODERATELY_ANOMALOUS"
    else:
        verdict = "WITHIN_NORMAL_RANGE"

    payload = {
        "asset": entries[0].get("asset_name", "unknown"),
        "fair_range": {"min": min(mins), "max": max(maxs)},
        "historical_mean": round(mu, 2),
        "historical_stddev": round(sigma, 2),
        "queried_price": price,
        "deviation_sigma": round(deviation_sigma, 2),
        "verdict": verdict,
    }
    return Artifact(name="market_analysis", parts=[DataPart(data=payload)])
