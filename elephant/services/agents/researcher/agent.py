"""
ELEPHANT — Researcher Agent
Receives research tasks, performs web search (stub in Stage 2),
stores findings in memory (stub), and notifies Orchestrator on completion.
"""
from __future__ import annotations
import asyncio
import logging
import httpx

from services.agents.base.agent import BaseAgent
from shared.schemas.message import BusMessage, EventType
from shared.config.base import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class ResearcherAgent(BaseAgent):
    def __init__(self):
        super().__init__("researcher")

    def subscribed_events(self) -> list[EventType]:
        return [EventType.agent_task_request]

    async def handle_message(self, msg: BusMessage) -> None:
        if msg.recipient_agent and msg.recipient_agent != self.agent_name:
            return

        payload   = msg.payload or {}
        task_id   = str(msg.task_id or payload.get("task_id", ""))
        brief     = payload.get("brief", {})
        topic     = brief.get("topic", "unknown")

        self._current_task_id = task_id
        logger.info("researcher_task_started", extra={"task_id": task_id, "topic": topic[:80]})

        try:
            # Stage 2 stub: simulates research time
            # Stage 5: replace with actual web_search tool + document parser
            findings = await self._research(topic)
            # Stage 3: write findings to Qdrant via Memory Agent
            await self._store_findings(task_id, topic, findings)
            # Report completion to orchestrator
            await self._complete_task(task_id, outputs=[findings])
            logger.info("researcher_task_completed", extra={"task_id": task_id})
        except Exception as exc:
            logger.error("researcher_task_failed", extra={"task_id": task_id, "error": str(exc)})
            await self._fail_task(task_id, str(exc))
        finally:
            self._current_task_id = None

    async def _research(self, topic: str) -> str:
        """
        Stage 2 stub: returns a placeholder findings document.
        Stage 5: Uses web_search tool + headless browser + PDF parser.
        """
        await asyncio.sleep(1)
        return (
            f"# Research Findings: {topic}\n\n"
            f"[Stage 2 Stub] Web research not yet connected. "
            f"Will use SerpAPI/DuckDuckGo + browser automation in Stage 5.\n\n"
            f"**Key topics to investigate:** {topic}\n"
            f"**Uncertainty flags:** Research engine not connected.\n"
        )

    async def _store_findings(self, task_id: str, topic: str, findings: str) -> None:
        """Stage 3: Will write chunks to Qdrant + update Neo4j knowledge graph."""
        logger.debug("researcher_memory_write_stub", extra={"task_id": task_id})

    async def _complete_task(self, task_id: str, outputs: list[str]) -> None:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"{settings.ORCHESTRATOR_URL}/tasks/{task_id}/complete",
                params={"cost_usd": 0.0},
                json=outputs,
            )

    async def _fail_task(self, task_id: str, error: str) -> None:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"{settings.ORCHESTRATOR_URL}/tasks/{task_id}/fail",
                params={"error": error},
            )


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/app")
    from shared.logging.config import configure_logging
    configure_logging("agent_researcher", settings.LOG_LEVEL)
    asyncio.run(ResearcherAgent().start())
