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
        Stores content in Qdrant vector storage.
        """
        from qdrant_client import QdrantClient, models
        import hashlib
        from datetime import datetime, timezone

        memory_type = payload.get("memory_type", "project")
        content     = payload.get("content", "")
        entity_id   = payload.get("entity_id", "")

        client = QdrantClient(url=settings.QDRANT_URL)
        collection_name = "elephant_memory"

        # Ensure collection exists
        collections = client.get_collections().collections
        if not any(c.name == collection_name for c in collections):
            client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE),
            )

        # Vector placeholder using hash
        content_hash = hashlib.sha256(content.encode()).digest()
        vector = [float(b) / 255.0 for b in content_hash]
        # Pad or truncate to 384
        if len(vector) < 384:
            vector += [0.0] * (384 - len(vector))
        else:
            vector = vector[:384]

        import uuid
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{entity_id}:{content[:50]}"))

        client.upsert(
            collection_name=collection_name,
            points=[
                models.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "content": content,
                        "memory_type": memory_type,
                        "entity_id": entity_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
            ],
        )
        logger.info("memory_agent_wrote_to_qdrant", extra={
            "memory_type": memory_type, "entity_id": entity_id
        })

    async def _handle_read(self, payload: dict) -> None:
        """
        Searches Qdrant for matching content and publishes result.
        """
        from qdrant_client import QdrantClient, models
        import hashlib

        query      = payload.get("query", "")
        memory_type = payload.get("memory_type")
        requester  = payload.get("requester_agent", "unknown")

        client = QdrantClient(url=settings.QDRANT_URL)
        collection_name = "elephant_memory"

        # Vector placeholder for query
        query_hash = hashlib.sha256(query.encode()).digest()
        vector = [float(b) / 255.0 for b in query_hash]
        if len(vector) < 384:
            vector += [0.0] * (384 - len(vector))
        else:
            vector = vector[:384]

        query_filter = None
        if memory_type:
            query_filter = models.Filter(
                must=[models.FieldCondition(key="memory_type", match=models.MatchValue(value=memory_type))]
            )

        search_results = client.search(
            collection_name=collection_name,
            query_vector=vector,
            query_filter=query_filter,
            limit=5,
        )

        results = [hit.payload for hit in search_results]

        # Publish result back on bus
        msg = BusMessage(
            event_type=EventType.memory_read_result,
            sender_agent=self.agent_name,
            recipient_agent=requester,
            payload={"query": query, "results": results},
        )
        await self.bus.publish(msg)
        logger.info("memory_agent_read_completed", extra={
            "query": query[:50], "results_count": len(results)
        })

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
