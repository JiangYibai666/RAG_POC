from __future__ import annotations

import asyncio
import json

from rich.console import Console
from rich.panel import Panel

from a2a.client import A2AClient
from a2a.types import Message, TaskRequest, TaskState, TextPart

console = Console()


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
                    console.print(Panel.fit(json.dumps(part.data, indent=2), title="Final Report"))
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
