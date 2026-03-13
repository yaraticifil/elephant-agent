from __future__ import annotations
import asyncio
import logging
from services.agents.base.agent import BaseAgent
from shared.schemas.message import BusMessage, EventType
from shared.logging.config import configure_logging
from shared.config.base import get_settings

settings = get_settings()
configure_logging("agent_mask", settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

class MaskAgent(BaseAgent):
    def __init__(self):
        super().__init__("mask")

    async def handle_message(self, msg: BusMessage) -> None:
        logger.info(f"Mask handling message: {msg.event_type}")
        if msg.event_type == EventType.agent_task_request:
            task = msg.payload
            title = task.get("title", "")

            # Simple Masking Logic (e.g. replace "Company XYZ" or "My Password" with [SANSÜRLENDİ])
            sensitive_keywords = ["my company", "my password", "my ip", "credit card"]

            for keyword in sensitive_keywords:
                if keyword in title.lower():
                    logger.info(f"Masking detected sensitive info: '{keyword}'")
                    title = title.replace(keyword, "[SANSÜRLENDİ]")

            task["title"] = title

            # Send the clean task to the Planner (Cloud)
            forward_msg = BusMessage(
                event_type=EventType.agent_task_request,
                task_id=msg.task_id,
                sender_agent="mask",
                recipient_agent="planner",
                payload=task,
            )
            await self.bus.publish(forward_msg)

if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/app")
    agent = MaskAgent()
    asyncio.run(agent.start())
