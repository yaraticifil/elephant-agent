from typing import Dict, Any, TypedDict, Literal
import logging

logger = logging.getLogger("orchestrator.graph")

class AgentState(TypedDict):
    task_id: str
    task_title: str
    task_type: str
    status: str
    current_agent: str
    is_sensitive: bool
    requires_cloud: bool
    context: Dict[str, Any]

def route_task(state: AgentState) -> Literal["gatekeeper", "end"]:
    logger.info(f"Routing task {state['task_id']} to gatekeeper")
    return "gatekeeper"

def run_gatekeeper(state: AgentState) -> AgentState:
    logger.info(f"Gatekeeper inspecting task {state['task_id']}")
    if "sensitive" in state["task_title"].lower() or "dark" in state["task_title"].lower():
        state["requires_cloud"] = False
        state["is_sensitive"] = True
    else:
        state["requires_cloud"] = True
        state["is_sensitive"] = False
    state["current_agent"] = "gatekeeper"
    return state

def gatekeeper_decide(state: AgentState) -> Literal["shadow", "mask"]:
    if state["requires_cloud"]:
        return "mask"
    else:
        return "shadow"

def run_mask(state: AgentState) -> AgentState:
    logger.info(f"Mask applying PII redaction for task {state['task_id']}")
    state["current_agent"] = "mask"
    return state

def run_planner(state: AgentState) -> AgentState:
    logger.info(f"Planner processing task in Cloud with Vertex AI for task {state['task_id']}")
    state["current_agent"] = "planner"
    return state

def run_shadow(state: AgentState) -> AgentState:
    logger.info(f"Shadow processing task locally for task {state['task_id']}")
    state["current_agent"] = "shadow"
    return state

try:
    from langgraph.graph import StateGraph, START, END

    workflow = StateGraph(AgentState)

    workflow.add_node("gatekeeper", run_gatekeeper)
    workflow.add_node("mask", run_mask)
    workflow.add_node("planner", run_planner)
    workflow.add_node("shadow", run_shadow)

    # v0.3 API: use add_edge(START, ...) instead of set_entry_point()
    workflow.add_edge(START, "gatekeeper")

    workflow.add_conditional_edges(
        "gatekeeper",
        gatekeeper_decide,
        {
            "mask": "mask",
            "shadow": "shadow"
        }
    )

    workflow.add_edge("mask", "planner")
    workflow.add_edge("planner", END)
    workflow.add_edge("shadow", END)

    app = workflow.compile()

except ImportError:
    logger.warning("langgraph not installed. Run `pip install langgraph`.")
    app = None
