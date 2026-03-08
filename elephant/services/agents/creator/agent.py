"""
ELEPHANT — Creator Agent
Receives content briefs, drafts content in Salim's voice using the Model Router,
writes drafts to project memory, dispatches to Critic for review.
"""
from __future__ import annotations
import asyncio
import logging
import httpx

from services.agents.base.agent import BaseAgent
from shared.schemas.message import BusMessage, EventType
from shared.config.base import get_settings
from shared.messaging.events import build_agent_task_request

settings = get_settings()
logger = logging.getLogger(__name__)


class CreatorAgent(BaseAgent):
    def __init__(self):
        super().__init__("creator")

    def subscribed_events(self) -> list[EventType]:
        return [EventType.agent_task_request]

    async def handle_message(self, msg: BusMessage) -> None:
        if msg.recipient_agent and msg.recipient_agent != self.agent_name:
            return

        payload = msg.payload or {}
        task_id = str(msg.task_id or payload.get("task_id", ""))
        brief   = payload.get("brief", {})
        topic   = brief.get("topic", "unknown topic")
        research_context = brief.get("research_context", "")

        self._current_task_id = task_id
        logger.info("creator_task_started", extra={"task_id": task_id, "topic": topic[:80]})

        try:
            draft = await self._draft_content(topic, research_context)
            await self._complete_task(task_id, outputs=[draft])

            # Dispatch to Critic for review
            parent_task_id = payload.get("parent_task_id")
            all_subtasks   = payload.get("all_subtask_ids", [])
            await self._dispatch_to_critic(task_id, draft, topic, parent_task_id, all_subtasks)
            logger.info("creator_draft_sent_to_critic", extra={"task_id": task_id})
        except Exception as exc:
            logger.error("creator_task_failed", extra={"task_id": task_id, "error": str(exc)})
            await self._fail_task(task_id, str(exc))
        finally:
            self._current_task_id = None

    async def _draft_content(self, topic: str, research: str) -> str:
        """
        Stage 2 stub: returns a template draft.
        Stage 5: Calls Model Router → Claude-3.5-Sonnet with voice profile + research context.
        """
        await asyncio.sleep(1)
        return (
            f"# Draft: {topic}\n\n"
            f"[Stage 2 Stub] Model Router not yet connected. "
            f"Real content generation via Claude-3.5-Sonnet in Stage 5.\n\n"
            f"**Topic:** {topic}\n\n"
            f"**Research context provided:** {'Yes' if research else 'No'}\n\n"
            f"---\n*Voice confidence: N/A (stub)*"
        )

    async def _dispatch_to_critic(
        self, task_id: str, draft: str, topic: str,
        parent_task_id: str | None, all_subtasks: list
    ) -> None:
        """Send draft to Critic for quality review."""
        msg = build_agent_task_request(
            sender=self.agent_name,
            recipient="critic",
            task_id=task_id,
            payload={
                "task_id": task_id,
                "parent_task_id": parent_task_id,
                "draft": draft,
                "brief": {"topic": topic},
                "all_subtask_ids": all_subtasks,
            }
        )
        await self.bus.publish(msg)

    async def _complete_task(self, task_id: str, outputs: list[str]) -> None:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"{settings.ORCHESTRATOR_URL}/tasks/{task_id}/complete",
                params={"cost_usd": 0.005},
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
    configure_logging("agent_creator", settings.LOG_LEVEL)
    asyncio.run(CreatorAgent().start())
