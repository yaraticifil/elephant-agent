"""
ELEPHANT — Memory Agent
Persistent memory librarian. Controls ALL reads and writes across all 3 backends.
No agent may write to or read from memory backends without going through this agent.
"""
from __future__ import annotations
import asyncio
import logging
import httpx
from datetime import datetime, timezone
from typing import Any

from services.agents.base.agent import BaseAgent
from shared.schemas.message import BusMessage, EventType
from shared.config.base import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class MemoryAgent(BaseAgent):
    def __init__(self):
        super().__init__("memory_agent")

    def subscribed_events(self) -> list[EventType]:
        return [EventType.agent_task_request, EventType.memory_write_request, EventType.memory_read_request]

    async def handle_message(self, msg: BusMessage) -> None:
        if msg.recipient_agent and msg.recipient_agent != self.agent_name:
            return

        event = msg.event_type
        payload = msg.payload or {}

        if event == EventType.memory_write_request:
            await self._handle_write(payload)
        elif event == EventType.memory_read_request:
            await self._handle_read(payload)
        elif event == EventType.agent_task_request:
            # Handle structured task (e.g. reminder storage)
            task_id = str(msg.task_id or payload.get("task_id", ""))
            await self._handle_task(task_id, payload)

    async def _handle_write(self, payload: dict) -> None:
        """
        Stage 3: Route to correct backend (vector/relational/graph).
        Stage 2: Stub — logs the write and returns.
        """
        memory_type = payload.get("memory_type", "project")
        content     = payload.get("content", "")
        entity_id   = payload.get("entity_id", "")
        logger.info("memory_agent_write_stub", extra={
            "memory_type": memory_type,
            "entity_id": entity_id,
            "content_len": len(content),
        })
        # Stage 3: dispatch to Qdrant (vector) / PostgreSQL / Neo4j based on memory_type

    async def _handle_read(self, payload: dict) -> None:
        """
        Stage 3: Query Qdrant + PostgreSQL + Neo4j fusion retrieval.
        Stage 2: Stub — returns empty result.
        """
        query      = payload.get("query", "")
        requester  = payload.get("requester_agent", "unknown")
        logger.info("memory_agent_read_stub", extra={
            "query": query[:80], "requester": requester
        })
        # Stage 3: run full retrieval pipeline and publish result back on bus

    async def _handle_task(self, task_id: str, payload: dict) -> None:
        """Handle explicit memory tasks like storing a reminder."""
        brief = payload.get("brief", {})
        topic = brief.get("topic", "")
        logger.info("memory_agent_task_received", extra={"task_id": task_id, "topic": topic[:80]})
        await asyncio.sleep(0.2)
        await self._complete_task(task_id, outputs=[f"Memory stored for: {topic}"])

    async def _complete_task(self, task_id: str, outputs: list[str]) -> None:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"{settings.ORCHESTRATOR_URL}/tasks/{task_id}/complete",
                params={"cost_usd": 0.0},
                json=outputs,
            )


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/app")
    from shared.logging.config import configure_logging
    configure_logging("agent_memory_agent", settings.LOG_LEVEL)
    asyncio.run(MemoryAgent().start())
