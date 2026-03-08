"""
ELEPHANT — Watchdog Agent (Stage 2)
Monitors agent heartbeats via Redis, escalates stale tasks.
DB-free Stage 2 version — full PostgreSQL integration in Stage 3.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from services.agents.base.agent import BaseAgent
from shared.schemas.message import BusMessage, EventType
from shared.messaging.events import build_alert_event
from shared.config.base import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

MISSED_HEARTBEAT_MULTIPLIER = 2


class WatchdogAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_name="watchdog")
        # In-memory heartbeat registry (Stage 2 — Redis/DB in Stage 3)
        self._last_heartbeat: dict[str, datetime] = {}
        self._stale_tasks: set[str] = set()

    async def _run_loop(self) -> None:
        """Main watchdog loop — checks heartbeats every HEARTBEAT_INTERVAL."""
        while self._running:
            await self._check_heartbeats()
            await asyncio.sleep(settings.HEARTBEAT_INTERVAL_SECONDS)

    async def _check_heartbeats(self) -> None:
        """
        Stage 2: Checks timestamp of last known heartbeat per agent.
        Publishes alert if an agent has not heartbeated in 2x interval.
        """
        now = datetime.now(timezone.utc)
        threshold = timedelta(seconds=settings.HEARTBEAT_INTERVAL_SECONDS * MISSED_HEARTBEAT_MULTIPLIER)

        for agent_name, last_beat in list(self._last_heartbeat.items()):
            if now - last_beat > threshold:
                logger.warning(
                    "watchdog_agent_stale",
                    extra={"agent": agent_name, "last_beat": last_beat.isoformat()}
                )
                alert = build_alert_event(
                    sender="watchdog",
                    message=f"Agent {agent_name} has stopped sending heartbeats",
                    severity="warning",
                    detail={"agent": agent_name, "last_beat": last_beat.isoformat()},
                )
                try:
                    await self.bus.publish(alert)
                except Exception as exc:
                    logger.error(f"watchdog_alert_publish_error: {exc}")

    async def _handle_message(self, msg: BusMessage) -> None:
        """Track heartbeats from all agents."""
        if msg.event_type == EventType.agent_heartbeat:
            agent_name = msg.sender_agent
            self._last_heartbeat[agent_name] = datetime.now(timezone.utc)
            logger.debug(f"watchdog_heartbeat_received | agent={agent_name}")

    def _get_subscribed_events(self) -> list[EventType]:
        return [EventType.agent_heartbeat]


async def main():
    from shared.logging.config import configure_logging
    configure_logging("agent_watchdog")
    agent = WatchdogAgent()
    await agent.start()
    try:
        await agent._run_loop()
    finally:
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(main())
