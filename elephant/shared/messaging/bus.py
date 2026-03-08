from __future__ import annotations
import json
import logging
from typing import Any, Callable, Awaitable
import redis.asyncio as aioredis
from shared.schemas.message import BusMessage, EventType

logger = logging.getLogger(__name__)

STREAM_NAME = "elephant:bus"
CONSUMER_GROUP = "elephant_cg"


class MessageBus:
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self._client: aioredis.Redis | None = None

    async def connect(self) -> None:
        self._client = await aioredis.from_url(
            self.redis_url, decode_responses=True, socket_connect_timeout=5
        )
        try:
            await self._client.xgroup_create(
                STREAM_NAME, "elephant_default_cg", id="0", mkstream=True
            )
        except Exception:
            pass
        logger.info("message_bus_connected")

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()

    async def publish(self, message: BusMessage) -> str:
        if not self._client:
            raise RuntimeError("MessageBus not connected")
        msg_id = await self._client.xadd(
            STREAM_NAME, {"data": message.model_dump_json()}
        )
        logger.debug(
            "bus_published",
            extra={"event_type": message.event_type, "sender": message.sender_agent}
        )
        return msg_id

    async def subscribe(
        self,
        consumer_name: str,
        handler: Callable[[BusMessage], Awaitable[None]],
        event_filter: list[EventType] | None = None,
        block_ms: int = 5000,
    ) -> None:
        cg_name = f"elephant_cg_{consumer_name}"
        try:
            await self._client.xgroup_create(
                STREAM_NAME, cg_name, id="0", mkstream=True
            )
        except Exception:
            pass

        while True:
            try:
                messages = await self._client.xreadgroup(
                    groupname=cg_name,
                    consumername=consumer_name,
                    streams={STREAM_NAME: ">"},
                    count=10,
                    block=block_ms,
                )
                if not messages:
                    continue
                for _, entries in messages:
                    for msg_id, fields in entries:
                        try:
                            bus_msg = BusMessage.model_validate_json(fields["data"])
                            if event_filter and bus_msg.event_type not in event_filter:
                                await self._client.xack(STREAM_NAME, cg_name, msg_id)
                                continue
                            await handler(bus_msg)
                            await self._client.xack(STREAM_NAME, cg_name, msg_id)
                        except Exception as exc:
                            logger.error(
                                "bus_message_error",
                                extra={"msg_id": msg_id, "error": str(exc)}
                            )
                            await self._client.xack(STREAM_NAME, cg_name, msg_id)
            except Exception as exc:
                logger.error("bus_subscribe_loop_error", extra={"error": str(exc)})
                import asyncio
                await asyncio.sleep(2)
