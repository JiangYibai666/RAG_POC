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


def parse_intent(query: str) -> dict:
    user_match = _USER_RE.search(query)
    price = _extract_price(query)
    return {
        "user_id": user_match.group(0).upper() if user_match else "U000",
        "asset": "Tesla Model X" if "tesla" in query.lower() else "unknown_asset",
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
    sigma = float(market.get("deviation_sigma", 0.0))
    new_accounts = int(tx.get("new_account_counterparties", 0))
    if sigma >= 5 and new_accounts >= 2:
        return "CRITICAL"
    if sigma >= 3:
        return "HIGH"
    if sigma >= 2:
        return "MEDIUM"
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
