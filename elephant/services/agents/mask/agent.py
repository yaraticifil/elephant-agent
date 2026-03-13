from __future__ import annotations
import asyncio
import logging
import re
from services.agents.base.agent import BaseAgent
from shared.schemas.message import BusMessage, EventType
from shared.config.base import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class MaskAgent(BaseAgent):
    def __init__(self):
        super().__init__("mask")

    async def handle_message(self, msg: BusMessage) -> None:
        logger.info(f"Mask handling message: {msg.event_type}")
        if msg.event_type == EventType.agent_task_request:
            task = msg.payload
            title = task.get("title", "")

            # Case-insensitive masking
            sensitive_keywords = ["my company", "my password", "my ip", "credit card"]

            masked_title = title
            for keyword in sensitive_keywords:
                # Use case-insensitive regex replace
                pattern = re.compile(re.escape(keyword), re.IGNORECASE)
                if pattern.search(masked_title):
                    logger.info(f"Masking detected sensitive info: '{keyword}'")
                    masked_title = pattern.sub("[SANSÜRLENDİ]", masked_title)

            task["title"] = masked_title

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
    from shared.logging.config import configure_logging
    configure_logging("agent_mask", settings.LOG_LEVEL)
    agent = MaskAgent()
    asyncio.run(agent.start())
