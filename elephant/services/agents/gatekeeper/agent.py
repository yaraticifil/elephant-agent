from __future__ import annotations
import asyncio
import logging
from services.agents.base.agent import BaseAgent
from shared.schemas.message import BusMessage, EventType
from shared.config.base import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class GatekeeperAgent(BaseAgent):
    def __init__(self):
        super().__init__("gatekeeper")

    async def handle_message(self, msg: BusMessage) -> None:
        logger.info(f"Gatekeeper handling message: {msg.event_type}")
        if msg.event_type == EventType.agent_task_request:
            task = msg.payload
            title = task.get("title", "").lower()

            # Simulated Mistral 7B (Fast) prompt routing logic
            if "sensitive" in title or "dark" in title or "local" in title:
                logger.warning(f"Task '{title}' flagged as SENSITIVE. Routing to Shadow Agent (Local).")
                task["requires_cloud"] = False
                task["is_sensitive"] = True
            else:
                logger.info(f"Task '{title}' flagged as CLEAN. Routing to Planner Agent (Cloud).")
                task["requires_cloud"] = True
                task["is_sensitive"] = False

            # Pass to Mask if cloud is required, else directly to Shadow
            next_agent = "mask" if task["requires_cloud"] else "shadow"

            # Forward the task to the next agent
            forward_msg = BusMessage(
                event_type=EventType.agent_task_request,
                task_id=msg.task_id,
                sender_agent="gatekeeper",
                recipient_agent=next_agent,
                payload=task,
            )
            await self.bus.publish(forward_msg)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/app")
    from shared.logging.config import configure_logging
    configure_logging("agent_gatekeeper", settings.LOG_LEVEL)
    agent = GatekeeperAgent()
    asyncio.run(agent.start())
