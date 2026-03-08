from __future__ import annotations
import asyncio
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import httpx
from services.agents.base.agent import BaseAgent
from shared.schemas.message import BusMessage, EventType
from shared.schemas.task import TaskCreate, TaskBrief, TaskType, TaskMode, TaskOrigin
from shared.logging.config import configure_logging
from shared.config.base import get_settings

settings = get_settings()
configure_logging("agent_interacter", settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


class InteracterAgent(BaseAgent):
    def __init__(self):
        super().__init__("interacter")

    def subscribed_events(self) -> list[EventType]:
        return [EventType.task_completed, EventType.task_escalated, EventType.system_alert]

    async def handle_message(self, msg: BusMessage) -> None:
        if msg.event_type == EventType.system_alert:
            severity = msg.payload.get("severity", "info")
            message = msg.payload.get("message", "")
            logger.warning("system_alert_received", extra={"severity": severity, "msg": message})
        elif msg.event_type == EventType.task_completed:
            logger.info("task_completed_received", extra={"task_id": str(msg.task_id)})
        elif msg.event_type == EventType.task_escalated:
            logger.warning("task_escalated_received", extra={"task_id": str(msg.task_id)})

    async def create_task_via_api(self, task_create: TaskCreate) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{settings.ORCHESTRATOR_URL}/tasks",
                json=task_create.model_dump(mode="json"),
            )
            resp.raise_for_status()
            return resp.json()


interacter_agent = InteracterAgent()


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(interacter_agent.start())
    yield


http_app = FastAPI(title="ELEPHANT Interacter", version="0.1.0", lifespan=lifespan)
http_app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@http_app.get("/health")
async def health():
    return {"service": "interacter", "status": "ok"}


@http_app.post("/input", status_code=201)
async def receive_input(body: dict):
    """
    Stage 1: accepts structured JSON input.
    Stage 5: will add natural language parsing.

    Expected body:
    {
        "title": "Do some research on X",
        "task_type": "research",
        "mode": "work",
        "brief": {"topic": "X"}
    }
    """
    task = TaskCreate(
        title=body.get("title", "Untitled task"),
        task_type=TaskType(body.get("task_type", "system")),
        mode=TaskMode(body.get("mode", "work")),
        origin=TaskOrigin.user,
        brief=TaskBrief(**body.get("brief", {})),
        tags=body.get("tags", []),
    )
    result = await interacter_agent.create_task_via_api(task)
    logger.info("task_created_via_interacter", extra={"task_id": result.get("task_id")})
    return {"task_id": result.get("task_id"), "status": result.get("status")}


if __name__ == "__main__":
    import sys
    import uvicorn
    sys.path.insert(0, "/app")
    uvicorn.run("services.agents.interacter.agent:http_app", host="0.0.0.0", port=8010, reload=False)
