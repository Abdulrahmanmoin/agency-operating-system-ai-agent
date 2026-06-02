"""Build the LangGraph state graph wiring every agent node + routing."""

from langgraph.graph import END, START, StateGraph

from agencyos.agents import (
    clarification,
    executor,
    manager,
    planning,
    proposal,
    requirement,
    risk,
    task_generation,
    transcription,
    validator,
)
from agencyos.graph.routing import manager_router, validator_router
from agencyos.graph.state import AgencyState


def build_graph():
    g = StateGraph(AgencyState)

    # Nodes
    g.add_node("manager", manager.run)
    g.add_node("transcription", transcription.run)
    g.add_node("requirement", requirement.run)
    g.add_node("clarification", clarification.run)
    g.add_node("planning", planning.run)
    g.add_node("task_generation", task_generation.run)
    g.add_node("risk", risk.run)
    g.add_node("proposal", proposal.run)
    g.add_node("validator", validator.run)
    g.add_node("executor", executor.run)

    # Edges
    g.add_edge(START, "manager")

    # Manager routes dynamically
    g.add_conditional_edges(
        "manager",
        manager_router,
        {
            "transcription": "transcription",
            "requirement": "requirement",
            "clarification": "clarification",
            "planning": "planning",
            "task_generation": "task_generation",
            "risk": "risk",
            "proposal": "proposal",
            "validator": "validator",
            "executor": "executor",
            "__end__": END,
        },
    )

    # Every specialist returns to Manager
    for node in [
        "transcription",
        "requirement",
        "clarification",
        "planning",
        "task_generation",
        "risk",
        "proposal",
    ]:
        g.add_edge(node, "manager")

    # Validator has its own router
    g.add_conditional_edges(
        "validator",
        validator_router,
        {"manager": "manager", "executor": "executor"},
    )

    g.add_edge("executor", END)

    return g
