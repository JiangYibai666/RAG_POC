from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from a2a.types import TaskEvent, TaskRequest, TaskResponse, TaskState


StreamHandler = Callable[[TaskRequest], AsyncIterator[TaskEvent]]


def _to_sse(event: TaskEvent) -> str:
    payload = event.model_dump(mode="json")
    return f"data: {json.dumps(payload, ensure_ascii=True)}\n\n"


def create_a2a_router(stream_handler: StreamHandler) -> APIRouter:
    router = APIRouter(prefix="/tasks", tags=["a2a"])

    @router.post("/send", response_model=TaskResponse)
    async def send_task(request: TaskRequest) -> TaskResponse:
        last_event: Optional[TaskEvent] = None
        async for event in stream_handler(request):
            last_event = event

        if last_event is None:
            raise HTTPException(status_code=500, detail="agent returned empty response")

        if last_event.state == TaskState.FAILED:
            return TaskResponse(task_id=request.task_id, state=TaskState.FAILED, error=last_event.message)

        return TaskResponse(task_id=request.task_id, state=last_event.state, artifact=last_event.artifact)

    @router.post("/sendSubscribe")
    async def send_task_subscribe(request: TaskRequest) -> StreamingResponse:
        async def event_generator() -> AsyncIterator[str]:
            async for event in stream_handler(request):
                yield _to_sse(event)

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    return router
