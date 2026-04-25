from __future__ import annotations
import asyncio
import logging
from services.agents.base.agent import BaseAgent
from shared.schemas.message import BusMessage, EventType
from shared.config.base import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class ListenerAgent(BaseAgent):
    def __init__(self):
        super().__init__("listener")

    async def handle_message(self, msg: BusMessage) -> None:
        logger.info(f"Listener handling message: {msg.event_type}")
        if msg.event_type == EventType.agent_task_request:
            task = msg.payload
            logger.info("Listening to audio and converting to text (Mock STT)")
            task["title"] = task.get("title", "") + " (transcribed by listener)"

            # Forward directly to gatekeeper
            forward_msg = BusMessage(
                event_type=EventType.agent_task_request,
                task_id=msg.task_id,
                sender_agent="listener",
                recipient_agent="gatekeeper",
                payload=task,
            )
            await self.bus.publish(forward_msg)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/app")
    from shared.logging.config import configure_logging
    configure_logging("agent_listener", settings.LOG_LEVEL)
    agent = ListenerAgent()
    asyncio.run(agent.start())
