from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class EventType(str, Enum):
    task_created = "task.created"
    task_assigned = "task.assigned"
    task_status_changed = "task.status_changed"
    task_completed = "task.completed"
    task_failed = "task.failed"
    task_cancelled = "task.cancelled"
    task_escalated = "task.escalated"
    agent_heartbeat = "agent.heartbeat"
    agent_task_request = "agent.task_request"
    agent_task_result = "agent.task_result"
    agent_feedback = "agent.feedback"
    system_alert = "system.alert"
    system_cost_threshold = "system.cost_threshold"
    system_agent_restart = "system.agent_restart"
    system_mode_change = "system.mode_change"
    approval_requested = "approval.requested"
    approval_granted = "approval.granted"
    approval_rejected = "approval.rejected"
    memory_write_request = "memory.write_request"
    memory_read_request = "memory.read_request"
    memory_read_result = "memory.read_result"


class AlertSeverity(str, Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


class BusMessage(BaseModel):
    message_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_type: EventType
    sender_agent: str
    recipient_agent: str | None = None
    task_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=3, ge=1, le=5)
    requires_ack: bool = False
    ttl_seconds: int = 300
    correlation_id: UUID | None = None
