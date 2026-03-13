from __future__ import annotations
import asyncio
import logging
from services.agents.base.agent import BaseAgent
from shared.schemas.message import BusMessage, EventType
from shared.logging.config import configure_logging
from shared.config.base import get_settings

settings = get_settings()
configure_logging("agent_shadow", settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

class ShadowAgent(BaseAgent):
    def __init__(self):
        super().__init__("shadow")

    async def handle_message(self, msg: BusMessage) -> None:
        logger.info(f"Shadow handling message: {msg.event_type}")
        if msg.event_type == EventType.agent_task_request:
            task = msg.payload
            title = task.get("title", "")

            logger.info(f"Shadow Agent processing sensitive task locally: '{title}'")
            # Mock Shadow Action
            task["status"] = "completed"
            task["outputs"] = ["Processed locally by Shadow Agent."]

            # Send completion
            completion_msg = BusMessage(
                event_type=EventType.task_completed,
                task_id=msg.task_id,
                sender_agent="shadow",
                recipient_agent="orchestrator",
                payload=task,
            )
            await self.bus.publish(completion_msg)

if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/app")
    agent = ShadowAgent()
    asyncio.run(agent.start())
