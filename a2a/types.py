from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field


class TaskState(str, Enum):
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"


class TextPart(BaseModel):
    type: Literal["text"] = "text"
    text: str


class DataPart(BaseModel):
    type: Literal["data"] = "data"
    data: dict[str, Any]


Part = Union[TextPart, DataPart]


class Message(BaseModel):
    message_id: str = Field(default_factory=lambda: f"msg_{uuid4().hex[:10]}")
    role: Literal["user", "agent"]
    parts: list[Part]


class Artifact(BaseModel):
    artifact_id: str = Field(default_factory=lambda: f"art_{uuid4().hex[:10]}")
    name: str
    parts: list[Part]


class AgentSkill(BaseModel):
    skill_id: str
    name: str
    description: str


class AgentCard(BaseModel):
    agent_name: str
    description: str
    skills: list[AgentSkill]


class TaskRequest(BaseModel):
    task_id: str = Field(default_factory=lambda: f"task_{uuid4().hex[:10]}")
    session_id: str = Field(default_factory=lambda: f"sess_{uuid4().hex[:10]}")
    source_agent: str
    target_agent: str
    message: Message


class TaskEvent(BaseModel):
    task_id: str
    state: TaskState
    message: Optional[str] = None
    artifact: Optional[Artifact] = None


class TaskResponse(BaseModel):
    task_id: str
    state: TaskState
    artifact: Optional[Artifact] = None
    error: Optional[str] = None
