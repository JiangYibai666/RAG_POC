from __future__ import annotations

import asyncio
import json

from rich.console import Console
from rich.panel import Panel

from a2a.client import A2AClient
from a2a.types import Message, TaskRequest, TaskState, TextPart

console = Console()


def _format_report_summary(report: dict) -> str:
    risk_level = report.get("risk_level", "UNKNOWN")
    confidence = report.get("confidence", 0.0)
    anomaly_types = report.get("anomaly_types", [])
    anomaly_text = ", ".join(anomaly_types) if anomaly_types else "no clear anomaly types detected"

    market = report.get("market_analysis", {})
    tx = report.get("transaction_analysis", {})

    asset_name = market.get("asset") or report.get("parsed_intent", {}).get("asset", "该资产")
    fair_min = market.get("fair_range", {}).get("min")
    fair_max = market.get("fair_range", {}).get("max")
    queried_price = market.get("queried_price")
    sigma = market.get("deviation_sigma")
    new_counterparties = tx.get("new_account_counterparties", 0)

    parts = [
        f"The risk level for this investigation is {risk_level}.",
        f"The identified anomaly types are: {anomaly_text}.",
    ]

    if fair_min is not None and fair_max is not None and queried_price is not None and sigma is not None:
        parts.append(
            f"For {asset_name}, the estimated fair market range is about ${fair_min:,.0f} to ${fair_max:,.0f}, but the actual transaction price reached ${queried_price:,.0f}, which is about {sigma:.2f}σ away from the mean and is therefore highly anomalous."
        )

    if new_counterparties:
        parts.append(
            f"The transaction analysis also found {new_counterparties} counterparties with new accounts within 7 days, which further increases related-party risk."
        )

    recommended_action = report.get("recommended_action", "REVIEW_MANUALLY")
    parts.append(f"The recommended action is {recommended_action}. The model confidence is {confidence:.2f}, which means this assessment is highly reliable.")

    return "".join(parts)


async def ask_once(query: str) -> None:
    request = TaskRequest(
        source_agent="CLI",
        target_agent="HostAgent",
        message=Message(role="user", parts=[TextPart(text=query)]),
    )
    client = A2AClient(timeout=120.0)
    try:
        response = await client.send(request)
        if response.state == TaskState.FAILED:
            console.print(f"[red]{response.error or 'HostAgent request failed'}[/red]")
            return

        if response.artifact is not None:
            for part in response.artifact.parts:
                if getattr(part, "type", "") == "data":
                    report = part.data
                    console.print(Panel.fit(json.dumps(report, indent=2), title="Final Report"))
                    console.print()
                    console.print(Panel.fit(_format_report_summary(report), title="Summary", border_style="cyan"))
    finally:
        await client.close()


def run_cli() -> None:
    console.print(Panel.fit("AML Investigation CLI (type 'exit' to quit)", title="A2A-AML-POC"))
    while True:
        query = input("> ").strip()
        if not query:
            continue
        if query.lower() in {"exit", "quit"}:
            break
        asyncio.run(ask_once(query))
