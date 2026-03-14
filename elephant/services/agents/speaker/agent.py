from __future__ import annotations
import asyncio
import logging
from services.agents.base.agent import BaseAgent
from shared.schemas.message import BusMessage, EventType
from shared.config.base import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class SpeakerAgent(BaseAgent):
    def __init__(self):
        super().__init__("speaker")

    def subscribed_events(self) -> list[EventType]:
        """Subscribe to task_completed events to convert results to speech."""
        return [EventType.task_completed]

    async def handle_message(self, msg: BusMessage) -> None:
        logger.info(f"Speaker handling message: {msg.event_type}")
        if msg.event_type == EventType.task_completed:
            task = msg.payload
            outputs = task.get("outputs", [])
            output_text = outputs[0] if outputs else task.get("title", "Görev tamamlandı.")
            
            # Publish a speak request for the UI
            speak_msg = BusMessage(
                event_type=EventType.speak_request,
                sender_agent="speaker",
                payload={"text": f"Halledildi Mösyö. {output_text[:200]}"},
                task_id=msg.task_id
            )
            await self.bus.publish(speak_msg)
            logger.info("Speaker published speak_request")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/app")
    from shared.logging.config import configure_logging
    configure_logging("agent_speaker", settings.LOG_LEVEL)
    agent = SpeakerAgent()
    asyncio.run(agent.start())
