from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class TaskType(str, Enum):
    research = "research"
    content_creation = "content_creation"
    image_generation = "image_generation"
    strategy = "strategy"
    report = "report"
    publish = "publish"
    reminder = "reminder"
    personal = "personal"
    system = "system"


class TaskStatus(str, Enum):
    pending = "pending"
    queued = "queued"
    active = "active"
    awaiting_review = "awaiting_review"
    awaiting_approval = "awaiting_approval"
    blocked = "blocked"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    escalated = "escalated"


class TaskPriority(int, Enum):
    critical = 1
    high = 2
    standard = 3
    low = 4
    idle = 5


class TaskMode(str, Enum):
    work = "work"
    life = "life"


class TaskOrigin(str, Enum):
    user = "user"
    watchdog_schedule = "watchdog_schedule"
    agent_spawn = "agent_spawn"
    api_webhook = "api_webhook"


class TaskRiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class TaskBrief(BaseModel):
    topic: str = ""
    format: str = ""
    platform: str = ""
    constraints: list[str] = Field(default_factory=list)
    additional: dict[str, Any] = Field(default_factory=dict)


class TaskCreate(BaseModel):
    title: str = Field(..., max_length=120)
    task_type: TaskType
    mode: TaskMode = TaskMode.work
    origin: TaskOrigin = TaskOrigin.user
    brief: TaskBrief = Field(default_factory=TaskBrief)
    priority: TaskPriority = TaskPriority.standard
    assigned_agent: str | None = None
    parent_task_id: UUID | str | None = None
    depends_on: list[UUID] = Field(default_factory=list)
    deadline: datetime | None = None
    success_criteria: str = ""
    risk_level: TaskRiskLevel = TaskRiskLevel.low
    tags: list[str] = Field(default_factory=list)


class TaskRead(BaseModel):
    task_id: UUID
    created_at: datetime
    updated_at: datetime
    title: str
    task_type: TaskType
    mode: TaskMode
    origin: TaskOrigin
    brief: TaskBrief
    priority: int
    status: TaskStatus
    assigned_agent: str | None
    parent_task_id: UUID | None
    subtask_ids: list[UUID]
    depends_on: list[UUID]
    deadline: datetime | None
    success_criteria: str
    risk_level: TaskRiskLevel
    requires_approval: bool
    approval_status: str
    cost_usd: float
    retry_count: int
    max_retries: int
    tags: list[str]
    outputs: list[str]

    class Config:
        from_attributes = True


class TaskUpdate(BaseModel):
    status: TaskStatus | None = None
    assigned_agent: str | None = None
    priority: int | None = None
    cost_usd: float | None = None
    outputs: list[str] | None = None
    approval_status: str | None = None
