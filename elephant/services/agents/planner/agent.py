"""
ELEPHANT — Planner Agent
Receives goals, queries memory, decomposes into a workflow DAG,
and dispatches tasks to the Orchestrator via the message bus.
"""
from __future__ import annotations
import asyncio
import logging
import uuid
from typing import Any
import httpx

from services.agents.base.agent import BaseAgent
from shared.schemas.message import BusMessage, EventType
from shared.schemas.task import TaskCreate, TaskBrief, TaskType, TaskMode, TaskOrigin, TaskRiskLevel
from shared.config.base import get_settings
from shared.config.persona import ELEPHANT_PERSONA
from shared.config.llm import PLANNER_MODEL, call_vertex_model
from shared.messaging.events import build_agent_task_request

settings = get_settings()
logger = logging.getLogger(__name__)

# ── VERTEX AI GROUNDING (Google Search) ────────────────────────────────────
def do_vertex_grounded_search(query: str) -> str:
    logger.info(f"Using Vertex AI Grounding (Google Search) for query: {query}")
    try:
        from google.cloud import aiplatform
        from vertexai.preview.generative_models import GenerativeModel, Tool
        import vertexai

        # Initialize Vertex AI with standard application default credentials
        # (Must be provided by the environment, e.g., GOOGLE_APPLICATION_CREDENTIALS)
        try:
            vertexai.init()
        except Exception as e:
            logger.warning(f"Vertex AI not initialized properly, falling back. Error: {e}")
            return f"[Simulated Vertex AI Grounded Result for '{query}' - Credentials missing]"

        # Use Gemini 1.5 Pro with Google Search Grounding Tool (Gemini required for Search tools)
        tool = Tool.from_google_search_retrieval(google_search_retrieval={})
        model = GenerativeModel("gemini-1.5-pro-002", tools=[tool])

        prompt = f"Perform a comprehensive Google search and analysis for the following query: {query}"
        response = model.generate_content(prompt)

        if response.text:
            return response.text
        return f"[Vertex AI Search returned empty result for '{query}']"

    except ImportError:
         logger.warning("google-cloud-aiplatform not installed.")
         return f"[Fallback Search Result for '{query}']"
    except Exception as e:
        logger.warning(f"Vertex AI Grounding error: {e}")
        return f"[Fallback Search Result for '{query}']"

# ──────────────────────────────────────────────────────────────────────────────
# TASK TYPE ROUTING: defines which agent handles each task type
# ──────────────────────────────────────────────────────────────────────────────
TASK_TYPE_AGENT_MAP: dict[TaskType, str] = {
    TaskType.research: "researcher",
    TaskType.content_creation: "creator",
    TaskType.strategy: "creator",
    TaskType.image_generation: "visual",
    TaskType.report: "reporter",
    TaskType.publish: "executor",
    TaskType.reminder: "memory_agent",
    TaskType.personal: "creator",
    TaskType.system: "orchestrator",
}

# ──────────────────────────────────────────────────────────────────────────────
# WORKFLOW TEMPLATES: canonical pipelines per goal type
# ──────────────────────────────────────────────────────────────────────────────
WORKFLOW_TEMPLATES: dict[str, list[dict]] = {
    "research": [
        {"step": 1, "agent": "researcher", "type": TaskType.research,   "label": "Deep-dive research & source gathering"},
        {"step": 2, "agent": "reporter",   "type": TaskType.report,     "label": "Synthesize findings into structured report"},
    ],
    "content_creation": [
        {"step": 1, "agent": "researcher", "type": TaskType.research,   "label": "Background research"},
        {"step": 2, "agent": "creator",    "type": TaskType.content_creation,   "label": "Draft content in Salim's voice"},
        {"step": 3, "agent": "critic",     "type": TaskType.system,     "label": "Quality gate: tone & brand check"},
        {"step": 4, "agent": "auditor",    "type": TaskType.system,     "label": "Compliance check + approval token"},
        {"step": 5, "agent": "executor",   "type": TaskType.publish,    "label": "Publish via approved channel"},
    ],
    "strategy": [
        {"step": 1, "agent": "researcher", "type": TaskType.research,   "label": "Market & competitive research"},
        {"step": 2, "agent": "creator",    "type": TaskType.strategy,   "label": "Draft strategic document"},
        {"step": 3, "agent": "critic",     "type": TaskType.system,     "label": "Strategic critique & alignment"},
        {"step": 4, "agent": "reporter",   "type": TaskType.report,     "label": "Final strategic brief"},
    ],
    "image_generation": [
        {"step": 1, "agent": "visual",     "type": TaskType.image_generation,      "label": "Generate visual assets"},
        {"step": 2, "agent": "critic",     "type": TaskType.system,     "label": "Brand consistency review"},
        {"step": 3, "agent": "auditor",    "type": TaskType.system,     "label": "Content compliance check"},
    ],
    "report": [
        {"step": 1, "agent": "reporter",   "type": TaskType.report,     "label": "Compile and format report"},
    ],
    "default": [
        {"step": 1, "agent": "researcher", "type": TaskType.research,   "label": "Research"},
        {"step": 2, "agent": "creator",    "type": TaskType.content_creation,   "label": "Create output"},
        {"step": 3, "agent": "critic",     "type": TaskType.system,     "label": "Review"},
    ],
}


def _classify_goal(title: str, task_type: TaskType) -> str:
    """Classify a goal into a workflow template key."""
    title_lower = title.lower()
    if task_type == TaskType.research:
        return "research"
    if task_type in (TaskType.content_creation, TaskType.publish):
        return "content_creation"
    if task_type == TaskType.strategy:
        return "strategy"
    if task_type == TaskType.image_generation:
        return "image_generation"
    if task_type == TaskType.report:
        return "report"
    # Heuristic title-based detection
    if any(k in title_lower for k in ("write", "create", "draft", "post", "linkedin", "tweet")):
        return "content_creation"
    if any(k in title_lower for k in ("strategy", "strategic", "roadmap", "plan")):
        return "strategy"
    if any(k in title_lower for k in ("image", "visual", "design", "logo", "banner")):
        return "image_generation"
    if any(k in title_lower for k in ("report", "brief", "summary", "digest")):
        return "report"
    return "research"


class PlannerAgent(BaseAgent):
    """
    The Planner:
    - Subscribes to task_created events
    - Queries memory for relevant context (Stage 3 — stubbed here)
    - Decomposes the goal into a workflow DAG
    - Creates subtasks on the Orchestrator API
    - Dispatches first subtask to the appropriate agent
    """

    def __init__(self):
        super().__init__("planner")
        self._workflow_state: dict[str, dict] = {}

    def subscribed_events(self) -> list[EventType]:
        return [EventType.task_created, EventType.agent_task_request, EventType.task_completed]

    async def handle_message(self, msg: BusMessage) -> None:
        if msg.event_type == EventType.task_created:
            await self._handle_task_created(msg)
        elif msg.event_type == EventType.agent_task_request:
            # Direct task dispatch to planner (e.g. from interacter)
            if msg.recipient_agent == self.agent_name:
                await self._handle_task_created(msg)
        elif msg.event_type == EventType.task_completed:
            await self._handle_step_completed(msg)

    # ──────────────────────────────────────────────────────────────────────────
    async def _handle_task_created(self, msg: BusMessage) -> None:
        payload = msg.payload or {}
        task_id   = str(msg.task_id or payload.get("task_id", ""))
        title     = payload.get("title", "Untitled")
        task_type_raw = payload.get("task_type", "research")
        mode_raw  = payload.get("mode", "work")

        # Only plan work-mode tasks unless we see explicit planner assignment
        if mode_raw == "life":
            logger.info("planner_skipping_life_mode_task", extra={"task_id": task_id})
            return

        try:
            task_type = TaskType(task_type_raw)
        except ValueError:
            task_type = TaskType.research

        logger.info("planner_received_goal", extra={
            "task_id": task_id, "title": title, "task_type": task_type_raw
        })

        # --- THINKING PHASE ---
        logger.info("planner_thinking_started", extra={"task_id": task_id})
        # In a real scenario, we'd call LLM here to get the <thought> block. 
        # For now, we simulate the persona's strategic reasoning.
        thought = f"<thought>Mösyö'nün direktifi alındı: '{title}'. Konseyin stratejik hedeflerine uygun olarak görev dağılımı planlanıyor. Fil her zaman hazırdır.</thought>"
        logger.info(f"Elephant Thought: {thought}")
        # ----------------------

        # 1. Query memory (stub: returns empty context in Stage 2)
        memory_context = await self._retrieve_memory(title)

        # 1.5. If research-based, augment context via Vertex AI Grounding
        if task_type in (TaskType.research, TaskType.strategy):
            loop = asyncio.get_running_loop()
            grounded_info = await loop.run_in_executor(None, do_vertex_grounded_search, title)
            memory_context += "\n" + grounded_info
            logger.info("planner_grounding_applied", extra={"query": title})

        # 2. Decompose into DAG
        workflow_key = _classify_goal(title, task_type)
        template     = WORKFLOW_TEMPLATES.get(workflow_key, WORKFLOW_TEMPLATES["default"])

        logger.info("planner_dag_constructed", extra={
            "parent_task_id": task_id,
            "workflow": workflow_key,
            "steps": len(template),
        })

        # 3. Create subtasks via Orchestrator API
        subtask_ids: list[str] = []
        for step in template:
            subtask = await self._create_subtask(
                title=f"[{step['step']}/{len(template)}] {step['label']}",
                task_type=step["type"],
                parent_task_id=task_id,
                assigned_agent=step["agent"],
                brief_topic=title,
                memory_context=memory_context,
                mode=TaskMode(mode_raw),
            )
            if subtask:
                subtask_ids.append(subtask.get("task_id", ""))

        # 4. Store workflow state
        self._workflow_state[task_id] = {
            "subtask_ids": subtask_ids,
            "current_step": 0,
            "workflow_key": workflow_key,
            "template": template,
            "title": title,
            "memory_context": memory_context,
            "mode": mode_raw,
        }

        # 5. Dispatch first subtask to its agent
        if template and subtask_ids:
            first_step = template[0]
            first_task_id = subtask_ids[0]
            await self._dispatch_to_agent(
                agent=first_step["agent"],
                task_id=first_task_id,
                title=f"{first_step['label']} — {title}",
                payload={
                    "task_id": first_task_id,
                    "parent_task_id": task_id,
                    "brief": {"topic": title, "memory_context": memory_context},
                    "workflow_key": workflow_key,
                    "all_subtask_ids": subtask_ids,
                }
            )
            logger.info("planner_dispatched_first_step", extra={
                "agent": first_step["agent"],
                "task_id": first_task_id,
                "parent": task_id,
            })

    # ──────────────────────────────────────────────────────────────────────────
    async def _retrieve_memory(self, query: str) -> str:
        """
        Stage 2 stub — returns empty context.
        Stage 3: Will query Qdrant (vector) + PostgreSQL + Neo4j via Memory Agent.
        """
        logger.debug("planner_memory_query_stub", extra={"query": query[:80]})
        return ""

    async def _create_subtask(
        self,
        title: str,
        task_type: TaskType,
        parent_task_id: str,
        assigned_agent: str,
        brief_topic: str,
        memory_context: str,
        mode: TaskMode,
    ) -> dict | None:
        task_create = TaskCreate(
            title=title,
            task_type=task_type,
            mode=mode,
            origin=TaskOrigin.agent_spawn,
            assigned_agent=assigned_agent,
            parent_task_id=parent_task_id,
            brief=TaskBrief(
                topic=brief_topic,
                additional={"context": memory_context[:500]} if memory_context else {},
            ),
            risk_level=TaskRiskLevel.low,
        )
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{settings.ORCHESTRATOR_URL}/tasks",
                    json=task_create.model_dump(mode="json"),
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            logger.error("planner_subtask_create_failed", extra={"error": str(exc), "title": title})
            return None

    async def _handle_step_completed(self, msg: BusMessage) -> None:
        payload = msg.payload or {}
        parent_id = str(payload.get("parent_task_id", ""))

        if parent_id not in self._workflow_state:
            # We also check all_subtask_ids as a fallback
            all_ids = payload.get("all_subtask_ids", [])
            workflow_key = payload.get("workflow_key", "default")
            if not parent_id or not all_ids:
                return
            # Restore state if planner restarted
            self._workflow_state[parent_id] = {
                "subtask_ids": all_ids,
                "current_step": 0,
                "workflow_key": workflow_key,
                "template": WORKFLOW_TEMPLATES.get(workflow_key, WORKFLOW_TEMPLATES["default"]),
                "title": payload.get("brief", {}).get("topic", "Task"),
                "memory_context": payload.get("brief", {}).get("memory_context", ""),
                "mode": payload.get("mode", "work"),
            }

        state = self._workflow_state[parent_id]
        completed_task_id = str(msg.task_id or payload.get("task_id", ""))

        # Find index of completed task
        try:
            current_idx = state["subtask_ids"].index(completed_task_id)
            state["current_step"] = current_idx
        except ValueError:
            return

        next_idx = current_idx + 1
        if next_idx < len(state["subtask_ids"]):
            next_task_id = state["subtask_ids"][next_idx]
            next_step = state["template"][next_idx]

            await self._dispatch_to_agent(
                agent=next_step["agent"],
                task_id=next_task_id,
                title=f"{next_step['label']} — {state['title']}",
                payload={
                    "task_id": next_task_id,
                    "parent_task_id": parent_id,
                    "brief": {"topic": state["title"], "memory_context": state["memory_context"]},
                    "workflow_key": state["workflow_key"],
                    "all_subtask_ids": state["subtask_ids"],
                }
            )
            logger.info("planner_dispatched_next_step", extra={
                "agent": next_step["agent"],
                "task_id": next_task_id,
                "parent": parent_id,
                "step": f"{next_idx+1}/{len(state['subtask_ids'])}",
            })
        else:
            logger.info("planner_workflow_completed", extra={"parent_task_id": parent_id})
            del self._workflow_state[parent_id]

    async def _dispatch_to_agent(
        self, agent: str, task_id: str, title: str, payload: dict[str, Any]
    ) -> None:
        """Publish a task dispatch event on the message bus targeting a specific agent."""
        msg = build_agent_task_request(
            sender=self.agent_name,
            recipient=agent,
            task_id=task_id,
            payload=payload,
        )
        await self.bus.publish(msg)
        logger.info("planner_dispatched", extra={"agent": agent, "task_id": task_id})


# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/app")
    from shared.logging.config import configure_logging
    configure_logging("agent_planner", settings.LOG_LEVEL)
    asyncio.run(PlannerAgent().start())
