"""Intent-driven conversational graph.

One graph invocation = one user turn. The flow is:

    START -> intake -> (capabilities offer? -> END)
                    -> intent_classifier -> prerequisite_check
                          -> (interrupt: confirm prerequisites)
                          -> dispatch loop (run only the needed agents, in dependency order)
                          -> finalize -> END

Mid-turn pauses (prerequisite confirmation, and clarification HITL inside an agent) use
LangGraph `interrupt()`; the caller resumes with `Command(resume=...)`. State persists across
turns via the checkpointer the orchestrator supplies at compile time.
"""

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from agencyos.agents import manager
from agencyos.agents.registry import AGENTS, capabilities_text
from agencyos.graph.routing import (
    FULL_PIPELINE,
    _step_done,
    topological_order,
)
from agencyos.graph.state import AgencyState, AuditEntry, AuditPhase

_YES = {"y", "yes", "yeah", "yep", "sure", "ok", "okay", "do it", "proceed", "go ahead", "please"}


def _is_yes(answer: object) -> bool:
    if isinstance(answer, bool):
        return answer
    text = str(answer or "").strip().lower()
    return text in _YES or text.startswith("y")


# ─── Manager-driven control nodes ─────────────────────────────────────


def intake_node(state: AgencyState) -> AgencyState:
    """First node of a turn. If there's no actionable instruction and we haven't yet shown the
    capabilities menu, offer it."""
    msg = (state.last_user_message or "").strip()
    if not msg and not state.capabilities_offered:
        if state.audio_path:
            kind = "an audio recording"
        elif state.notes_path:
            kind = "your notes"
        else:
            kind = "some material"
        state.last_assistant_message = capabilities_text(kind)
        state.capabilities_offered = True
    return state


def intake_router(state: AgencyState) -> str:
    return "classify" if (state.last_user_message or "").strip() else "end"


async def intent_classifier_node(state: AgencyState) -> AgencyState:
    """Classify the user's message into target agents (LLM)."""
    intent = await manager.run.classify_intent(state)
    state.intent = intent
    state.scratch["executed"] = []  # reset per-turn execution log
    state.last_assistant_message = None
    state.audit_log.append(
        AuditEntry(
            agent="manager",
            phase=AuditPhase.ROUTE,
            content=f"intent: agents={intent.agents} full_pipeline={intent.full_pipeline} :: {intent.rationale}",
        )
    )
    return state


def prerequisite_check_node(state: AgencyState) -> AgencyState:
    """Decide the dispatch queue. May interrupt to ask the user about missing prerequisites."""
    intent = state.intent
    assert intent is not None

    if intent.full_pipeline:
        queue = topological_order(FULL_PIPELINE)
    elif not intent.agents:
        state.last_assistant_message = (
            "I'm not sure which of my capabilities that maps to. "
            "Could you rephrase, or ask for one of the things I listed?"
        )
        state.dispatch_queue = []
        return state
    else:
        confirmation = manager.run.resolve_prerequisites(state, intent)
        if confirmation is not None:
            answer = interrupt(
                {
                    "kind": "confirmation",
                    "question": confirmation.question,
                    "prerequisites": confirmation.prerequisites,
                    "target_agents": confirmation.target_agents,
                }
            )
            if _is_yes(answer):
                queue = topological_order(confirmation.prerequisites + confirmation.target_agents)
            else:
                state.last_assistant_message = (
                    "Okay — I won't run those prerequisites. Tell me what you'd like instead."
                )
                state.dispatch_queue = []
                return state
        else:
            queue = topological_order(intent.agents)

    # Never re-run an agent whose output already exists in state.
    state.dispatch_queue = [a for a in queue if not _step_done(state, a)]
    return state


def dispatch_router(state: AgencyState) -> str:
    """Pick the next agent to run, or finalize when the queue is empty."""
    return state.dispatch_queue[0] if state.dispatch_queue else "finalize"


def make_agent_node(agent_name: str):
    """Wrap a BaseAgent as a graph node that runs it and advances the dispatch queue.

    Normally the just-run agent sits at the head of the queue and is dropped. An agent's merge
    may instead rewrite the queue wholesale (e.g. the validator bouncing work back) and set
    `scratch['_queue_overridden']` — in that case we leave the queue exactly as it set it.
    """
    agent = AGENTS[agent_name]

    async def node(state: AgencyState) -> AgencyState:
        new_state = await agent(state)  # may interrupt() (e.g. clarification HITL)
        if new_state.scratch.pop("_queue_overridden", False):
            pass  # the agent's merge already set the next queue explicitly
        elif new_state.dispatch_queue and new_state.dispatch_queue[0] == agent_name:
            new_state.dispatch_queue = new_state.dispatch_queue[1:]
        else:
            new_state.dispatch_queue = [a for a in new_state.dispatch_queue if a != agent_name]
        new_state.scratch.setdefault("executed", []).append(agent_name)
        return new_state

    return node


def finalize_node(state: AgencyState) -> AgencyState:
    """Show the user what was produced this turn (the actual artifacts, not just status)."""
    if state.last_assistant_message:
        return state

    from agencyos.views import summarize

    intent = state.intent
    if intent is not None and intent.full_pipeline:
        scope = ["proposal", "validator", "executor"]  # headline outputs of a full run
    elif intent is not None and intent.agents:
        scope = intent.agents  # show what the user asked for (even if already present)
    else:
        scope = state.scratch.get("executed", [])

    body = summarize(state, scope)
    if body:
        state.last_assistant_message = body
    else:
        state.last_assistant_message = (
            "I'm not sure which of my capabilities that maps to — try e.g. "
            "'extract the requirements', 'plan it and flag the risks', or 'handle it end to end'."
        )
    return state


# ─── Graph assembly ───────────────────────────────────────────────────


def build_graph() -> StateGraph:
    g = StateGraph(AgencyState)

    # control nodes
    g.add_node("intake", intake_node)
    g.add_node("intent_classifier", intent_classifier_node)
    g.add_node("prerequisite_check", prerequisite_check_node)
    g.add_node("finalize", finalize_node)

    # specialist agent nodes (from the registry — manager excluded)
    for agent_name in AGENTS:
        g.add_node(agent_name, make_agent_node(agent_name))

    # dispatch routing map: any agent -> its own node, plus finalize
    dispatch_map = {name: name for name in AGENTS}
    dispatch_map["finalize"] = "finalize"

    g.add_edge(START, "intake")
    g.add_conditional_edges(
        "intake", intake_router, {"classify": "intent_classifier", "end": END}
    )
    g.add_edge("intent_classifier", "prerequisite_check")
    g.add_conditional_edges("prerequisite_check", dispatch_router, dispatch_map)

    # after each agent runs, route to the next queued agent (or finalize)
    for agent_name in AGENTS:
        g.add_conditional_edges(agent_name, dispatch_router, dispatch_map)

    g.add_edge("finalize", END)
    return g
