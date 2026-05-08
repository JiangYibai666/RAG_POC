from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import FastAPI

from a2a.server import create_a2a_router
from a2a.types import TaskEvent, TaskRequest, TaskState
from agents.transaction_agent.graph import run_transaction_graph
from storage.task_store import add_artifact, add_message, create_task, update_task_state


async def stream_handler(request: TaskRequest) -> AsyncIterator[TaskEvent]:
    create_task(request.task_id, request.session_id, request.source_agent, request.target_agent, TaskState.WORKING)
    add_message(request.task_id, request.message)

    yield TaskEvent(task_id=request.task_id, state=TaskState.WORKING, message="TransactionAgent: querying logs")
    await asyncio.sleep(0.05)

    artifact = run_transaction_graph(request.message)
    add_artifact(request.task_id, artifact)
    update_task_state(request.task_id, TaskState.COMPLETED)

    yield TaskEvent(task_id=request.task_id, state=TaskState.COMPLETED, message="TransactionAgent: completed", artifact=artifact)


def create_app() -> FastAPI:
    _app = FastAPI(title="TransactionAgent", version="0.1.0")
    _app.include_router(create_a2a_router(stream_handler))
    return _app


app = create_app()
