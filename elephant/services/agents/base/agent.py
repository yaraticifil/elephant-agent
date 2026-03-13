from __future__ import annotations
import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from shared.config.base import get_settings
from shared.messaging.bus import MessageBus
from shared.messaging.events import build_heartbeat_event
from shared.schemas.message import BusMessage, EventType
import httpx

settings = get_settings()
logger = logging.getLogger(__name__)

ALL_AGENT_NAMES = [
    "planner", "researcher", "creator", "visual", "critic",
    "memory_agent", "executor", "watchdog", "auditor", "interacter", "reporter",
    "gatekeeper", "shadow", "mask", "listener", "speaker"
]


class BaseAgent(ABC):
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.bus = MessageBus(settings.REDIS_URL)
        self._started_at = datetime.now(timezone.utc)
        self._running = False
        self._current_task_id: str | None = None
        self._tasks_completed = 0
        self._cost_today = 0.0

    async def start(self) -> None:
        await self.bus.connect()
        await self._register()
        self._running = True
        logger.info("agent_started", extra={"agent": self.agent_name})
        await asyncio.gather(
            self._heartbeat_loop(),
            self._subscribe_loop(),
        )

    async def stop(self) -> None:
        self._running = False
        await self.bus.disconnect()
        logger.info("agent_stopped", extra={"agent": self.agent_name})

    async def _register(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"{settings.ORCHESTRATOR_URL}/agents/register",
                    json={"agent_name": self.agent_name, "status": "healthy"},
                )
        except Exception:
            pass

    async def _heartbeat_loop(self) -> None:
        while self._running:
            try:
                msg = build_heartbeat_event(
                    self.agent_name,
                    "healthy",
                    self._current_task_id
                )
                await self.bus.publish(msg)
            except Exception as exc:
                logger.error("heartbeat_error", extra={"agent": self.agent_name, "error": str(exc)})
            await asyncio.sleep(settings.HEARTBEAT_INTERVAL_SECONDS)

    async def _subscribe_loop(self) -> None:
        await self.bus.subscribe(
            consumer_name=self.agent_name,
            handler=self._dispatch,
            event_filter=self.subscribed_events(),
        )

    async def _dispatch(self, msg: BusMessage) -> None:
        if msg.recipient_agent and msg.recipient_agent != self.agent_name:
            return
        await self.handle_message(msg)

    def subscribed_events(self) -> list[EventType]:
        return [EventType.agent_task_request]

    @abstractmethod
    async def handle_message(self, msg: BusMessage) -> None:
        ...
