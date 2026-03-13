#!/usr/bin/env python3
"""
ELEPHANT — Orchestrator Service (self-contained minimal)
Starts the FastAPI orchestrator with health endpoint and task routes.
"""
from __future__ import annotations
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("orchestrator")

# ── Shared bus (Redis) ─────────────────────────────────────────────────────
redis_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client
    import redis.asyncio as aioredis
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
    try:
        redis_client = aioredis.from_url(redis_url, decode_responses=True)
        await redis_client.ping()
        logger.info(f"orchestrator_ready | redis={redis_url}")
    except Exception as exc:
        logger.warning(f"redis_not_available: {exc}")
    yield
    if redis_client:
        await redis_client.aclose()
    logger.info("orchestrator_stopped")


app = FastAPI(title="ELEPHANT Orchestrator", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory task store (Stage 2 — PostgreSQL in Stage 3) ────────────────
import uuid
import json
from datetime import datetime, timezone
from typing import Any

_tasks: dict[str, dict] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── BusMessage-compatible event publishing ────────────────────────────────
def _build_bus_event(event_type: str, task_id: str, task: dict) -> str:
    """Build a BusMessage-compatible JSON string for Redis publishing."""
    from uuid import uuid4
    event = {
        "message_id": str(uuid4()),
        "timestamp": _now(),
        "event_type": event_type,
        "sender_agent": "orchestrator",
        "recipient_agent": None,
        "task_id": task_id,
        "payload": task,
        "priority": 3,
        "requires_ack": False,
        "ttl_seconds": 300,
        "correlation_id": None,
    }
    return json.dumps(event, default=str)


# ── ROUTES ────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"service": "orchestrator", "status": "ok", "version": "2.0.0"}


@app.post("/tasks", status_code=201)
async def create_task(body: dict):
    task_id = str(uuid.uuid4())
    task = {
        "task_id": task_id,
        "title": body.get("title", "Untitled"),
        "task_type": body.get("task_type", "research"),
        "mode": body.get("mode", "work"),
        "status": "queued",
        "origin": body.get("origin", "user"),
        "assigned_agent": body.get("assigned_agent", "gatekeeper"),
        "parent_task_id": body.get("parent_task_id"),
        "brief": body.get("brief", {}),
        "outputs": [],
        "cost_usd": 0.0,
        "created_at": _now(),
        "updated_at": _now(),
    }
    _tasks[task_id] = task
    logger.info(f"task_created | id={task_id} | title={task['title'][:60]}")

    # Process via LangGraph if available
    try:
        from services.orchestrator.graph import app as graph_app
        if graph_app:
            logger.info("routing_task_via_langgraph")
            initial_state = {
                "task_id": task_id,
                "task_title": task["title"],
                "task_type": task["task_type"],
                "status": "queued",
                "current_agent": "orchestrator",
                "is_sensitive": False,
                "requires_cloud": False,
                "context": task["brief"]
            }
            # Run graph async
            result = await graph_app.ainvoke(initial_state)
            logger.info(f"langgraph_result: {result}")
            task["status"] = "graph_processed"
    except ImportError as e:
        logger.warning(f"Could not import langgraph: {e}")
    except Exception as e:
        logger.error(f"Error in langgraph processing: {e}")

    # Publish to Redis bus (BusMessage-compatible format)
    if redis_client:
        bus_event = _build_bus_event("task.created", task_id, task)
        await redis_client.xadd("elephant:bus", {"data": bus_event})

    return task


@app.get("/tasks")
async def list_tasks(status: str | None = None, limit: int = 50):
    tasks = list(_tasks.values())
    if status:
        tasks = [t for t in tasks if t["status"] == status]
    return tasks[-limit:]


@app.get("/tasks/{task_id}")
async def get_task(task_id: str):
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


@app.post("/tasks/{task_id}/complete")
async def complete_task(task_id: str, outputs: list[str] = Body(default=[]), cost_usd: float = 0.0):
    task = _tasks.get(task_id)
    if not task:
        logger.warning(f"task_not_in_memory_creating_stub | id={task_id}")
        task = {
            "task_id": task_id,
            "title": f"Stub Task {task_id[:8]}",
            "status": "queued",
            "created_at": _now(),
        }
        _tasks[task_id] = task
    task["status"] = "completed"
    task["outputs"] = outputs
    task["cost_usd"] = cost_usd
    task["updated_at"] = _now()
    logger.info(f"task_completed | id={task_id}")

    # Publish task_completed event on bus
    if redis_client:
        bus_event = _build_bus_event("task.completed", task_id, task)
        await redis_client.xadd("elephant:bus", {"data": bus_event})

    return task


@app.post("/tasks/{task_id}/fail")
async def fail_task(task_id: str, error: str = "unknown"):
    task = _tasks.get(task_id)
    if not task:
        logger.warning(f"task_not_in_memory_creating_stub | id={task_id}")
        task = {
            "task_id": task_id,
            "title": f"Stub Task {task_id[:8]}",
            "status": "queued",
            "created_at": _now(),
        }
        _tasks[task_id] = task
    retries = task.get("retry_count", 0)
    if retries < 3:
        task["retry_count"] = retries + 1
        task["status"] = "queued"
    else:
        task["status"] = "escalated"
    task["updated_at"] = _now()
    logger.warning(f"task_failed | id={task_id} | retries={retries} | error={error}")
    return task


@app.delete("/tasks/{task_id}")
async def cancel_task(task_id: str, reason: str = "cancelled"):
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    task["status"] = "cancelled"
    task["updated_at"] = _now()
    return task


@app.put("/tasks/{task_id}")
async def update_task(task_id: str, body: dict):
    task = _tasks.get(task_id)
    if not task:
        logger.warning(f"task_not_in_memory_creating_stub | id={task_id}")
        task = {
            "task_id": task_id,
            "title": f"Stub Task {task_id[:8]}",
            "status": "queued",
            "created_at": _now(),
        }
        _tasks[task_id] = task
    task.update(body)
    task["updated_at"] = _now()
    return task


@app.get("/agents")
async def list_agents():
    """Return registered agents (stub — Stage 3 uses DB)."""
    return {"agents": [], "message": "Stage 2: agent registry not yet connected"}


@app.post("/agents/register")
async def register_agent(body: dict):
    logger.info(f"agent_registered | name={body.get('agent_name')} | status={body.get('status')}")
    return {"registered": True, "agent_name": body.get("agent_name")}


@app.get("/stream")
async def stream_events():
    """Server-Sent Events endpoint for real-time UI logging."""
    async def event_generator():
        if not redis_client:
            yield "data: {\"event_type\":\"system\",\"payload\":\"no_redis_connection\"}\n\n"
            return
            
        last_id = "$"
        while True:
            try:
                messages = await redis_client.xread(
                    streams={"elephant:bus": last_id}, count=10, block=2000
                )
                if messages:
                    for _, entries in messages:
                        for msg_id, fields in entries:
                            last_id = msg_id
                            yield f"data: {fields['data']}\n\n"
                else:
                    # Keep-alive comment
                    yield ": keepalive\n\n"
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"sse_stream_error: {e}")
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
