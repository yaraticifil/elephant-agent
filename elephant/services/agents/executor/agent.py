"""
ELEPHANT — Executor Agent
The ONLY agent that takes real-world actions.
Requires a cryptographically signed Auditor token (< 15 min old).
NEVER acts without a valid token. Never stores credentials in memory.
"""
from __future__ import annotations
import asyncio
import hashlib
import hmac
import json
import logging
import time
import httpx

from services.agents.base.agent import BaseAgent
from shared.schemas.message import BusMessage, EventType
from shared.config.base import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


def _validate_token(token: dict, task_id: str, secret: str) -> bool:
    """Verify HMAC token integrity and TTL."""
    try:
        expected_task = token.get("task_id")
        issued_at     = int(token.get("issued_at", 0))
        expires_at    = int(token.get("expires_at", 0))
        received_sig  = token.get("token", "")

        if expected_task != task_id:
            return False
        if time.time() > expires_at:
            return False  # token expired

        payload = f"{task_id}:{token.get('issued_by', 'auditor')}:{issued_at}:{expires_at}"
        expected_sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(received_sig, expected_sig)
    except Exception:
        return False


class ExecutorAgent(BaseAgent):
    def __init__(self):
        super().__init__("executor")
        self._secret = getattr(settings, "AUDITOR_TOKEN_SECRET", "elephant-auditor-secret-v1")

    def subscribed_events(self) -> list[EventType]:
        return [EventType.agent_task_request]

    async def handle_message(self, msg: BusMessage) -> None:
        if msg.recipient_agent and msg.recipient_agent != self.agent_name:
            return

        payload = msg.payload or {}
        task_id = str(msg.task_id or payload.get("task_id", ""))
        token   = payload.get("approval_token")
        action  = payload.get("action", "")

        # ── HARD SAFETY GATE ──────────────────────────────────────────────────
        if not token:
            logger.error("executor_blocked_no_token", extra={"task_id": task_id})
            return

        if not _validate_token(token, task_id, self._secret):
            logger.error("executor_blocked_invalid_token", extra={"task_id": task_id})
            await self._alert_invalid_token(task_id)
            return

        if action == "AWAITING_USER_APPROVAL":
            logger.info("executor_awaiting_user_approval", extra={"task_id": task_id})
            await self._set_awaiting_approval(task_id)
            return

        # ── Real execution (Stage 5: LinkedIn, email, calendar, etc.) ─────────
        self._current_task_id = task_id
        logger.info("executor_executing", extra={"task_id": task_id, "action": action})

        try:
            result = await self._execute(task_id, payload)
            await self._complete_task(task_id, outputs=[result])
            logger.info("executor_completed", extra={"task_id": task_id})
        except Exception as exc:
            logger.error("executor_failed", extra={"task_id": task_id, "error": str(exc)})
            await self._fail_task(task_id, str(exc))
        finally:
            self._current_task_id = None

    async def _execute(self, task_id: str, payload: dict) -> str:
        """
        Stage 2 stub: all actions are BLOCKED pending user approval.
        Stage 5: Real APIs — LinkedIn, email SMTP, calendar, CRM webhook.
        Credentials read from Vault at execution time ONLY.
        """
        await asyncio.sleep(0.3)
        return f"İnfaz durduruldu Mösyö. {task_id} numaralı görev için mühür bekleniyor. Tedbir her şeydir."

    async def _set_awaiting_approval(self, task_id: str) -> None:
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                await client.put(
                    f"{settings.ORCHESTRATOR_URL}/tasks/{task_id}",
                    json={"status": "awaiting_approval"},
                )
            except Exception as exc:
                logger.warning("executor_status_update_failed", extra={"error": str(exc)})

    async def _alert_invalid_token(self, task_id: str) -> None:
        from shared.messaging.events import build_alert_event
        await self.bus.publish(build_alert_event(
            self.agent_name,
            f"Executor blocked: invalid or expired Auditor token for task {task_id}",
            "critical",
            {"task_id": task_id},
        ))

    async def _complete_task(self, task_id: str, outputs: list[str]) -> None:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"{settings.ORCHESTRATOR_URL}/tasks/{task_id}/complete",
                params={"cost_usd": 0.0},
                json=outputs,
            )

    async def _fail_task(self, task_id: str, error: str) -> None:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"{settings.ORCHESTRATOR_URL}/tasks/{task_id}/fail",
                params={"error": error},
            )


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/app")
    from shared.logging.config import configure_logging
    configure_logging("agent_executor", settings.LOG_LEVEL)
    asyncio.run(ExecutorAgent().start())
