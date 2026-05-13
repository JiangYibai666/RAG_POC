from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Optional

from a2a.client import A2AClient
from a2a.types import Artifact, DataPart, Message, TaskEvent, TaskRequest, TaskState, TextPart
from storage.task_store import create_session, finalize_session


_USER_RE = re.compile(r"\bU\d{3,}\b", re.IGNORECASE)


def _extract_price(text: str) -> float:
    # Remove $ separators and commas, then find the largest number
    cleaned = text.replace(",", "").replace("$", " $")
    matches = re.findall(r"\$?\s*([0-9]+(?:\.[0-9]+)?)", cleaned)
    if not matches:
        return 0.0
    return max(float(m) for m in matches)


_ASSET_RE = re.compile(r"\bsold\s+(?:a|an)\s+(.+?)\s+for\b", re.IGNORECASE)


def parse_intent(query: str) -> dict:
    user_match = _USER_RE.search(query)
    price = _extract_price(query)
    asset_match = _ASSET_RE.search(query)
    asset = asset_match.group(1).strip() if asset_match else "unknown_asset"
    return {
        "user_id": user_match.group(0).upper() if user_match else "U000",
        "asset": asset,
        "transaction_amount": price,
        "transaction_type": "sale" if "sold" in query.lower() else "unknown",
        "investigation_goal": "Determine money laundering risk",
    }


def _extract_data(artifact: Optional[Artifact]) -> dict:
    if artifact is None:
        return {}
    for part in artifact.parts:
        if getattr(part, "type", "") == "data":
            return part.data
    return {}


def _risk_from_evidence(market: dict, tx: dict) -> str:
    # ── 第三层：综合风险裁定（HostAgent）────────────────────────────────────
    # 汇入 MarketAgent（价格侧）与 TransactionAgent（行为侧）的两路证据，
    # 通过多条件规则树输出最终 risk_level。

    # 从市场分析结果中取价格偏离 Z-score
    sigma = float(market.get("deviation_sigma", 0.0))
    # 从交易分析结果中取新开账户对手方数量与是否有结构化拆单
    new_accounts = int(tx.get("new_account_counterparties", 0))
    is_structuring = tx.get("structuring", {}).get("verdict") == "HIGH_RISK_STRUCTURING"

    # 规则 1：价格极端偏离（>= 10σ）单独触发 CRITICAL，无需行为侧佐证
    if sigma >= 10:
        return "CRITICAL"
    # 规则 2：价格显著异常（>= 5σ）且叠加任一行为侧风险信号 → CRITICAL
    if sigma >= 5 and (new_accounts >= 1 or is_structuring):
        return "CRITICAL"
    # 规则 3：价格高度异常（>= 3σ）→ HIGH
    if sigma >= 3:
        return "HIGH"
    # 规则 4：价格中度异常（>= 2σ）→ MEDIUM
    if sigma >= 2:
        return "MEDIUM"
    # 规则 5：价格正常，无其他触发条件 → LOW
    return "LOW"


async def run_host_investigation(task_request: TaskRequest) -> AsyncIterator[TaskEvent]:
    query = " ".join(part.text for part in task_request.message.parts if getattr(part, "type", "") == "text")
    parsed = parse_intent(query)
    create_session(task_request.session_id, query)

    yield TaskEvent(task_id=task_request.task_id, state=TaskState.WORKING, message="HostAgent: parse_intent done")

    client = A2AClient()
    try:
        market_req = TaskRequest(
            session_id=task_request.session_id,
            source_agent="HostAgent",
            target_agent="MarketAgent",
            message=Message(role="user", parts=[TextPart(text=query)]),
        )
        market_resp = await client.send(market_req)
        market_data = _extract_data(market_resp.artifact)
        yield TaskEvent(task_id=task_request.task_id, state=TaskState.WORKING, message="HostAgent: market evidence collected")

        tx_req = TaskRequest(
            session_id=task_request.session_id,
            source_agent="HostAgent",
            target_agent="TransactionAgent",
            message=Message(role="user", parts=[TextPart(text=f"Analyze user {parsed['user_id']} for suspicious patterns")]),
        )
        tx_resp = await client.send(tx_req)
        tx_data = _extract_data(tx_resp.artifact)
        yield TaskEvent(task_id=task_request.task_id, state=TaskState.WORKING, message="HostAgent: transaction evidence collected")

        risk_level = _risk_from_evidence(market_data, tx_data)
        report = {
            "session_id": task_request.session_id,
            "risk_level": risk_level,
            "anomaly_types": [
                "PRICE_ANOMALY" if market_data.get("deviation_sigma", 0) >= 2 else "",
                "RELATED_PARTY_TRANSACTION" if tx_data.get("new_account_counterparties", 0) > 0 else "",
            ],
            "evidence_chain": [
                {
                    "step": 1,
                    "agent": "MarketAgent",
                    "finding": f"Price sigma deviation: {market_data.get('deviation_sigma', 0)}",
                },
                {
                    "step": 2,
                    "agent": "TransactionAgent",
                    "finding": f"New counterparties within 7 days: {tx_data.get('new_account_counterparties', 0)}",
                },
            ],
            "recommended_action": "FREEZE_AND_REPORT_SAR" if risk_level in {"HIGH", "CRITICAL"} else "REVIEW_MANUALLY",
            "confidence": 0.92 if risk_level in {"HIGH", "CRITICAL"} else 0.75,
            "parsed_intent": parsed,
            "market_analysis": market_data,
            "transaction_analysis": tx_data,
        }
        report["anomaly_types"] = [item for item in report["anomaly_types"] if item]

        finalize_session(task_request.session_id, report, risk_level)
        artifact = Artifact(name="aml_final_report", parts=[DataPart(data=report)])
        yield TaskEvent(
            task_id=task_request.task_id,
            state=TaskState.COMPLETED,
            message="HostAgent: report generated",
            artifact=artifact,
        )
    except Exception as exc:
        yield TaskEvent(
            task_id=task_request.task_id,
            state=TaskState.FAILED,
            message=f"HostAgent failed: {exc}",
        )
    finally:
        await client.close()
