from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from a2a.registry import AGENT_ENDPOINTS
from a2a.types import TaskEvent, TaskRequest, TaskResponse


class A2AClient:
    def __init__(self, timeout: float = 60.0) -> None:
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def send(self, request: TaskRequest) -> TaskResponse:
        endpoint = AGENT_ENDPOINTS[request.target_agent]
        resp = await self._client.post(f"{endpoint}/tasks/send", json=request.model_dump(mode="json"))
        resp.raise_for_status()
        return TaskResponse.model_validate(resp.json())

    async def send_subscribe(self, request: TaskRequest) -> AsyncIterator[TaskEvent]:
        endpoint = AGENT_ENDPOINTS[request.target_agent]
        async with self._client.stream(
            "POST",
            f"{endpoint}/tasks/sendSubscribe",
            json=request.model_dump(mode="json"),
            headers={"Accept": "text/event-stream"},
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                payload = json.loads(line[len("data: ") :])
                yield TaskEvent.model_validate(payload)
