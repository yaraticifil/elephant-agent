"""
ELEPHANT — Critic Agent
Quality gate — reviews content from Creator and scores it.
Uses a DIFFERENT model than Creator (architectural independence rule).
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

CRITIC_PASS_THRESHOLD = 70  # out of 100


class CriticAgent(BaseAgent):
    def __init__(self):
        super().__init__("critic")
        self._revision_counts: dict[str, int] = {}

    def subscribed_events(self) -> list[EventType]:
        return [EventType.agent_task_request]

    async def handle_message(self, msg: BusMessage) -> None:
        if msg.recipient_agent and msg.recipient_agent != self.agent_name:
            return

        payload   = msg.payload or {}
        task_id   = str(msg.task_id or payload.get("task_id", ""))
        draft     = payload.get("draft", "")
        brief     = payload.get("brief", {})
        topic     = brief.get("topic", "unknown")

        self._current_task_id = task_id
        logger.info("critic_review_started", extra={"task_id": task_id})

        try:
            score, critique = await self._review(draft, topic)
            revision_num = self._revision_counts.get(task_id, 0)

            if score >= CRITIC_PASS_THRESHOLD:
                logger.info("critic_approved", extra={"task_id": task_id, "score": score})
                await self._complete_task(task_id, outputs=[f"APPROVED (score={score})", critique])
                # Forward to Auditor for compliance check
                await self._dispatch_to_auditor(task_id, draft, topic, payload)
            elif revision_num >= 3:
                # Max revisions exceeded — escalate to user with best draft
                logger.warning("critic_max_revisions_exceeded", extra={"task_id": task_id})
                await self._complete_task(task_id, outputs=[f"ESCALATED (score={score})", critique])
            else:
                # Request revision from Creator
                self._revision_counts[task_id] = revision_num + 1
                logger.info("critic_requesting_revision", extra={
                    "task_id": task_id, "score": score, "revision": revision_num + 1
                })
                await self._request_revision(task_id, critique, topic, payload)
        except Exception as exc:
            logger.error("critic_failed", extra={"task_id": task_id, "error": str(exc)})
        finally:
            self._current_task_id = None

    async def _review(self, draft: str, topic: str) -> tuple[int, str]:
        """
        Stage 2 stub: returns a high-pass score for all drafts.
        Stage 5: Calls Model Router → GPT-4o (different from Creator which uses Claude).
        """
        await asyncio.sleep(0.5)
        score = 80  # stub: auto-pass
        critique = (
            f"[Stage 2 Stub] Auto-approval. "
            f"Stage 5 will use GPT-4o (independence rule: Creator uses Claude).\n"
            f"**Score:** {score}/100 | **Topic:** {topic}"
        )
        return score, critique

    async def _dispatch_to_auditor(
        self, task_id: str, draft: str, topic: str, parent_payload: dict
    ) -> None:
        msg = build_agent_task_request(
            sender=self.agent_name,
            recipient="auditor",
            task_id=task_id,
            payload={
                "task_id": task_id,
                "parent_task_id": parent_payload.get("parent_task_id"),
                "draft": draft,
                "brief": {"topic": topic},
                "all_subtask_ids": parent_payload.get("all_subtask_ids", []),
            }
        )
        await self.bus.publish(msg)

    async def _request_revision(
        self, task_id: str, critique: str, topic: str, parent_payload: dict
    ) -> None:
        msg = build_agent_task_request(
            sender=self.agent_name,
            recipient="creator",
            task_id=task_id,
            payload={
                "task_id": task_id,
                "parent_task_id": parent_payload.get("parent_task_id"),
                "brief": {"topic": topic, "critique": critique},
                "all_subtask_ids": parent_payload.get("all_subtask_ids", []),
            }
        )
        await self.bus.publish(msg)

    async def _complete_task(self, task_id: str, outputs: list[str]) -> None:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"{settings.ORCHESTRATOR_URL}/tasks/{task_id}/complete",
                params={"cost_usd": 0.003},
                json=outputs,
            )


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/app")
    from shared.logging.config import configure_logging
    configure_logging("agent_critic", settings.LOG_LEVEL)
    asyncio.run(CriticAgent().start())
