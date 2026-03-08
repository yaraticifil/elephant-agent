"""
ELEPHANT — Auditor Agent
Final compliance checkpoint between Critic approval and Executor action.
Issues HMAC-SHA256 signed approval tokens or structured rejections.
"""
from __future__ import annotations
import asyncio
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
import httpx

from services.agents.base.agent import BaseAgent
from shared.schemas.message import BusMessage, EventType
from shared.config.base import get_settings
from shared.messaging.events import build_agent_task_request

settings = get_settings()
logger = logging.getLogger(__name__)

TOKEN_TTL_SECONDS = 900  # 15 minutes per design doc
PII_KEYWORDS = ["ssn", "passport", "credit card", "bank account", "password", "api_key"]


def _sign_token(task_id: str, agent: str, secret: str) -> dict:
    """Generate a time-limited HMAC-SHA256 approval token."""
    issued_at = int(time.time())
    expires_at = issued_at + TOKEN_TTL_SECONDS
    payload = f"{task_id}:{agent}:{issued_at}:{expires_at}"
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return {
        "token": signature,
        "task_id": task_id,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "issued_by": "auditor",
    }


def _detect_pii(content: str) -> list[str]:
    """Simple keyword-based PII detector. Stage 5: replace with ML model."""
    found = [kw for kw in PII_KEYWORDS if kw.lower() in content.lower()]
    return found


class AuditorAgent(BaseAgent):
    def __init__(self):
        super().__init__("auditor")
        self._secret = getattr(settings, "AUDITOR_TOKEN_SECRET", "elephant-auditor-secret-v1")

    def subscribed_events(self) -> list[EventType]:
        return [EventType.agent_task_request]

    async def handle_message(self, msg: BusMessage) -> None:
        if msg.recipient_agent and msg.recipient_agent != self.agent_name:
            return

        payload = msg.payload or {}
        task_id = str(msg.task_id or payload.get("task_id", ""))
        draft   = payload.get("draft", "")
        brief   = payload.get("brief", {})
        topic   = brief.get("topic", "unknown")

        self._current_task_id = task_id
        logger.info("auditor_review_started", extra={"task_id": task_id})

        try:
            # 1. PII Detection — hard reject if found
            pii_found = _detect_pii(draft)
            if pii_found:
                reason = f"PII detected in content: {pii_found}"
                logger.error("auditor_hard_reject_pii", extra={"task_id": task_id, "pii": pii_found})
                await self._complete_task(task_id, outputs=[f"REJECTED: {reason}"])
                # Alert: send system_alert via bus
                from shared.messaging.events import build_alert_event
                await self.bus.publish(build_alert_event(
                    self.agent_name, reason, "critical", {"task_id": task_id}
                ))
                return

            # 2. Compliance check (stub in Stage 2)
            approved, rejection_reason = await self._compliance_check(draft, topic)

            if not approved:
                logger.warning("auditor_rejected", extra={"task_id": task_id, "reason": rejection_reason})
                await self._complete_task(task_id, outputs=[f"REJECTED: {rejection_reason}"])
                return

            # 3. Issue approval token
            token = _sign_token(task_id, self.agent_name, self._secret)
            logger.info("auditor_approved", extra={"task_id": task_id, "token_expires": token["expires_at"]})

            await self._complete_task(task_id, outputs=[f"APPROVED", json.dumps(token)])

            # 4. Dispatch to Executor with token
            await self._dispatch_to_executor(task_id, draft, topic, token, payload)

        except Exception as exc:
            logger.error("auditor_failed", extra={"task_id": task_id, "error": str(exc)})
        finally:
            self._current_task_id = None

    async def _compliance_check(self, content: str, topic: str) -> tuple[bool, str]:
        """
        Stage 2 stub: auto-approves all non-PII content.
        Stage 5: ML brand safety classifier + compliance rule engine.
        """
        await asyncio.sleep(0.3)
        return True, ""

    async def _dispatch_to_executor(
        self, task_id: str, draft: str, topic: str, token: dict, parent_payload: dict
    ) -> None:
        """
        IMPORTANT: In Stage 2, Executor is BLOCKED by default.
        This dispatch is queued as AWAITING_APPROVAL in the Orchestrator.
        Real execution requires explicit user approval via dashboard.
        """
        msg = build_agent_task_request(
            sender=self.agent_name,
            recipient="executor",
            task_id=task_id,
            payload={
                "task_id": task_id,
                "parent_task_id": parent_payload.get("parent_task_id"),
                "approval_token": token,
                "draft": draft,
                "brief": {"topic": topic},
                "action": "AWAITING_USER_APPROVAL",  # Executor will not act without user confirmation
            }
        )
        await self.bus.publish(msg)

    async def _complete_task(self, task_id: str, outputs: list[str]) -> None:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"{settings.ORCHESTRATOR_URL}/tasks/{task_id}/complete",
                params={"cost_usd": 0.0},
                json=outputs,
            )


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/app")
    from shared.logging.config import configure_logging
    configure_logging("agent_auditor", settings.LOG_LEVEL)
    asyncio.run(AuditorAgent().start())
