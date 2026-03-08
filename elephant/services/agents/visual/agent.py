"""
ELEPHANT — Visual Agent
Generates brand-consistent image and visual assets.
Stage 2: Stub. Stage 5: DALL-E 3 + Stability AI + local SDXL.
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


class VisualAgent(BaseAgent):
    def __init__(self):
        super().__init__("visual")

    def subscribed_events(self) -> list[EventType]:
        return [EventType.agent_task_request]

    async def handle_message(self, msg: BusMessage) -> None:
        if msg.recipient_agent and msg.recipient_agent != self.agent_name:
            return

        payload  = msg.payload or {}
        task_id  = str(msg.task_id or payload.get("task_id", ""))
        brief    = payload.get("brief", {})
        topic    = brief.get("topic", "brand image")
        style    = brief.get("style", "professional, modern")
        platform = brief.get("platform", "generic")
        private  = brief.get("private", False)

        self._current_task_id = task_id
        logger.info("visual_task_started", extra={"task_id": task_id, "topic": topic[:60]})

        try:
            asset = await self._generate_image(topic, style, platform, private)
            await self._complete_task(task_id, outputs=[asset])

            # Dispatch to Critic for brand review
            await self._dispatch_to_critic(task_id, asset, topic, payload)
            logger.info("visual_sent_to_critic", extra={"task_id": task_id})
        except Exception as exc:
            logger.error("visual_task_failed", extra={"task_id": task_id, "error": str(exc)})
            await self._fail_task(task_id, str(exc))
        finally:
            self._current_task_id = None

    async def _generate_image(self, topic: str, style: str, platform: str, private: bool) -> str:
        """
        Stage 2 stub.
        Stage 5 routing:
          - private=True   → local SDXL (GPU)
          - private=False  → DALL-E 3 / Stability AI
        """
        await asyncio.sleep(1)
        model_used = "local-sdxl-stub" if private else "dall-e-3-stub"
        return (
            f"[Stage 2 Stub] Image generation not yet connected.\n"
            f"Prompt: '{topic}' | Style: {style} | Platform: {platform}\n"
            f"Model (would use): {model_used}\n"
            f"Asset path: /assets/output/{task_id[:8]}_placeholder.png"
        )

    async def _dispatch_to_critic(self, task_id: str, asset: str, topic: str, parent_payload: dict) -> None:
        msg = build_agent_task_request(
            sender=self.agent_name,
            recipient="critic",
            task_id=task_id,
            payload={
                "task_id": task_id,
                "parent_task_id": parent_payload.get("parent_task_id"),
                "draft": asset,
                "brief": {"topic": topic, "type": "image"},
                "all_subtask_ids": parent_payload.get("all_subtask_ids", []),
            }
        )
        await self.bus.publish(msg)

    async def _complete_task(self, task_id: str, outputs: list[str]) -> None:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"{settings.ORCHESTRATOR_URL}/tasks/{task_id}/complete",
                params={"cost_usd": 0.04},
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
    configure_logging("agent_visual", settings.LOG_LEVEL)
    asyncio.run(VisualAgent().start())
