from __future__ import annotations
import asyncio
import logging
from services.agents.base.agent import BaseAgent
from shared.schemas.message import BusMessage, EventType
from shared.config.base import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class ShadowAgent(BaseAgent):
    def __init__(self):
        super().__init__("shadow")

    async def handle_message(self, msg: BusMessage) -> None:
        logger.info(f"Shadow handling message: {msg.event_type}")
        if msg.event_type == EventType.agent_task_request:
            task = msg.payload
            task_id = str(msg.task_id or task.get("task_id", ""))
            title = task.get("title", "")

            self._current_task_id = task_id
            logger.info(f"Shadow Agent processing sensitive task locally: '{title}'")

            try:
                # Mock Shadow Action — local processing
                result = f"Gölge ajan işini sessizce bitirdi Mösyö: {title}. Fil her şeyi görür."

                # Report completion to Orchestrator HTTP API
                await self._complete_task(task_id, outputs=[result])

                # Also publish task_completed on bus for Planner workflow progression
                completion_msg = BusMessage(
                    event_type=EventType.task_completed,
                    task_id=msg.task_id,
                    sender_agent="shadow",
                    payload={**task, "status": "completed", "outputs": [result]},
                )
                await self.bus.publish(completion_msg)
                logger.info("shadow_task_completed", extra={"task_id": task_id})
            except Exception as exc:
                logger.error("shadow_task_failed", extra={"task_id": task_id, "error": str(exc)})
                await self._fail_task(task_id, str(exc))
            finally:
                self._current_task_id = None


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/app")
    from shared.logging.config import configure_logging
    configure_logging("agent_shadow", settings.LOG_LEVEL)
    agent = ShadowAgent()
    asyncio.run(agent.start())
