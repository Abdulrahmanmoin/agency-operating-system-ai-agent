"""Routing + dependency resolution for the intent-driven orchestrator.

The system is conversational, not a fixed pipeline: the Manager classifies the user's intent
into a set of target agents, and we run only those agents (plus any prerequisites the user
confirms). This module owns the *dependency graph* between agents and the helpers that turn a
requested set of agents into an ordered, prerequisite-complete execution list.
"""

from agencyos.graph.state import AgencyState

# ─── Agent dependency graph ───────────────────────────────────────────
# Maps an agent -> the agents whose outputs it requires before it can run.
# (Input prerequisites like "audio file" or "transcript/notes" are checked via _step_done /
#  input presence, not listed here.)
DEPENDENCIES: dict[str, list[str]] = {
    "transcription": [],
    "requirement": [],
    "clarification": ["requirement"],
    "planning": ["requirement"],
    "task_generation": ["planning"],
    "risk": ["planning", "task_generation"],
    "proposal": ["requirement", "planning"],
    "validator": ["proposal"],
    # ClickUp ticket creation has no agent-output prerequisite: it works from a free-form request,
    # and opportunistically from the generated tasks if they already exist.
    "clickup": [],
}

# Agents that can act WITHOUT any meeting material (so the source-material gate must not refuse
# them). ClickUp can create a ticket from a plain free-form instruction.
MATERIAL_FREE_AGENTS: frozenset[str] = frozenset({"clickup"})

# Canonical order for a full end-to-end run ("do everything" intent).
FULL_PIPELINE: list[str] = [
    "requirement",
    "clarification",
    "planning",
    "task_generation",
    "risk",
    "proposal",
    "validator",
]

KNOWN_AGENTS: frozenset[str] = frozenset(DEPENDENCIES)


def _step_done(state: AgencyState, step: str) -> bool:
    """Whether an agent's output already exists in state (i.e. it need not run again)."""
    match step:
        case "transcription":
            return state.transcript is not None
        case "requirement":
            return state.requirements is not None
        case "clarification":
            # "done" only once every critical clarification has a user answer
            return bool(state.clarifications) and not any(
                c.user_answer is None and c.severity.value == "critical"
                for c in state.clarifications
            )
        case "planning":
            return state.plan is not None
        case "task_generation":
            return bool(state.tasks)
        case "risk":
            return bool(state.risks)
        case "proposal":
            return state.proposal is not None
        case "validator":
            return state.validation_report is not None and state.validation_report.approved
        case _:
            return False


def reset_agent_output(state: AgencyState, agent: str) -> None:
    """Clear an agent's stored output so it will run again (used for regenerate/redo)."""
    match agent:
        case "transcription":
            state.transcript = None
            state.transcript_meta = None
        case "requirement":
            state.requirements = None
        case "clarification":
            state.clarifications = []
        case "planning":
            state.plan = None
        case "task_generation":
            state.tasks = []
        case "risk":
            state.risks = []
        case "proposal":
            state.proposal = None
        case "validator":
            state.validation_report = None
            state.attempt_count.pop("validation", None)


def missing_prerequisites(state: AgencyState, agent: str) -> list[str]:
    """Transitively collect prerequisite agents for `agent` whose output isn't in state yet.

    Returned in dependency order (deepest prerequisites first), de-duplicated.
    """
    ordered: list[str] = []
    seen: set[str] = set()

    def visit(name: str) -> None:
        for dep in DEPENDENCIES.get(name, []):
            if dep in seen:
                continue
            visit(dep)
            if not _step_done(state, dep) and dep not in ordered:
                ordered.append(dep)
            seen.add(dep)

    visit(agent)
    return ordered


def topological_order(agents: list[str]) -> list[str]:
    """Order a requested set of agents (and only those) so dependencies come first.

    Unknown agent names are dropped. The input set is treated as the universe — we do NOT
    pull in prerequisites here (that's `missing_prerequisites`' job); we only order what's given.
    """
    requested = [a for a in agents if a in KNOWN_AGENTS]
    requested_set = set(requested)
    result: list[str] = []
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(name: str) -> None:
        if name in done or name not in requested_set:
            return
        if name in visiting:
            return  # cycle guard (DEPENDENCIES is a DAG, but be safe)
        visiting.add(name)
        for dep in DEPENDENCIES.get(name, []):
            visit(dep)
        visiting.discard(name)
        done.add(name)
        result.append(name)

    for a in requested:
        visit(a)
    return result
