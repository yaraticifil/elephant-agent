from __future__ import annotations
from typing import Any
from shared.schemas.message import BusMessage, EventType
from shared.schemas.task import TaskRead


def build_task_event(
    event_type: EventType,
    task: TaskRead,
    sender: str,
    recipient: str | None = None,
    payload: dict[str, Any] | None = None,
) -> BusMessage:
    base: dict[str, Any] = {
        "task_id": str(task.task_id),
        "task_type": task.task_type,
        "status": task.status,
        "title": task.title,
        "mode": task.mode,
    }
    if payload:
        base.update(payload)
    return BusMessage(
        event_type=event_type,
        sender_agent=sender,
        recipient_agent=recipient,
        task_id=task.task_id,
        payload=base,
        priority=task.priority,
    )


def build_alert_event(
    sender: str,
    message: str,
    severity: str,
    detail: dict[str, Any] | None = None,
) -> BusMessage:
    return BusMessage(
        event_type=EventType.system_alert,
        sender_agent=sender,
        payload={"message": message, "severity": severity, "detail": detail or {}},
        priority=1 if severity == "critical" else 3,
    )


def build_heartbeat_event(
    agent_name: str, status: str, task_id: str | None = None
) -> BusMessage:
    return BusMessage(
        event_type=EventType.agent_heartbeat,
        sender_agent=agent_name,
        recipient_agent="watchdog",
        payload={"agent_name": agent_name, "status": status, "current_task_id": task_id},
        requires_ack=False,
    )


def build_agent_task_request(
    sender: str,
    recipient: str,
    task_id: str,
    payload: dict[str, Any],
) -> BusMessage:
    """Build a direct agent-to-agent task dispatch message."""
    from uuid import UUID
    try:
        task_uuid = UUID(task_id)
    except (ValueError, AttributeError):
        task_uuid = None
    return BusMessage(
        event_type=EventType.agent_task_request,
        sender_agent=sender,
        recipient_agent=recipient,
        task_id=task_uuid,
        payload=payload,
        priority=2,
    )
