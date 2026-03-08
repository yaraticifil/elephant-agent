"""
ELEPHANT — Reporter Agent
Synthesizes data from agent logs and task records.
Produces daily briefings, project reports, and performance digests.
Read-only—never calls external APIs directly.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
import httpx

from services.agents.base.agent import BaseAgent
from shared.schemas.message import BusMessage, EventType
from shared.config.base import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class ReporterAgent(BaseAgent):
    def __init__(self):
        super().__init__("reporter")

    def subscribed_events(self) -> list[EventType]:
        return [EventType.agent_task_request, EventType.task_completed]

    async def handle_message(self, msg: BusMessage) -> None:
        if msg.recipient_agent and msg.recipient_agent != self.agent_name:
            return

        payload = msg.payload or {}
        task_id = str(msg.task_id or payload.get("task_id", ""))
        brief   = payload.get("brief", {})
        topic   = brief.get("topic", "System Report")
        report_type = payload.get("report_type", "research_digest")

        self._current_task_id = task_id
        logger.info("reporter_task_started", extra={"task_id": task_id, "type": report_type})

        try:
            report = await self._compile_report(report_type, topic, payload)
            await self._complete_task(task_id, outputs=[report])
            logger.info("reporter_task_completed", extra={"task_id": task_id})
        except Exception as exc:
            logger.error("reporter_task_failed", extra={"task_id": task_id, "error": str(exc)})
        finally:
            self._current_task_id = None

    async def _compile_report(self, report_type: str, topic: str, payload: dict) -> str:
        """
        Stage 2: generates a structured stub report.
        Stage 5: queries TaskDB + agent logs + analytics APIs.
        """
        await asyncio.sleep(0.5)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return (
            f"# ELEPHANT — {report_type.replace('_', ' ').title()}\n"
            f"**Generated:** {timestamp}\n"
            f"**Topic:** {topic}\n\n"
            f"---\n\n"
            f"## Summary\n"
            f"[Stage 2 Stub] Full data aggregation from TaskDB, agent logs, and analytics in Stage 5.\n\n"
            f"## Task Pipeline Status\n"
            f"- Parent Task ID: {payload.get('parent_task_id', 'N/A')}\n"
            f"- Subtasks: {payload.get('all_subtask_ids', [])}\n\n"
            f"## Next Steps\n"
            f"- Review findings with Researcher output\n"
            f"- Approve content via dashboard\n"
        )

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
    configure_logging("agent_reporter", settings.LOG_LEVEL)
    asyncio.run(ReporterAgent().start())
