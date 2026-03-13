from __future__ import annotations
import asyncio
import logging
from services.agents.base.agent import BaseAgent
from shared.schemas.message import BusMessage, EventType
from shared.logging.config import configure_logging
from shared.config.base import get_settings

settings = get_settings()
configure_logging("agent_speaker", settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

class SpeakerAgent(BaseAgent):
    def __init__(self):
        super().__init__("speaker")

    async def handle_message(self, msg: BusMessage) -> None:
        logger.info(f"Speaker handling message: {msg.event_type}")
        if msg.event_type == EventType.task_completed:
            task = msg.payload
            logger.info("Speaker converts text back to audio (Mock TTS)")
            logger.info(f"Speaker Output Audio: Halledildi Mösyö. {task.get('title')}")

if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/app")
    agent = SpeakerAgent()
    asyncio.run(agent.start())
