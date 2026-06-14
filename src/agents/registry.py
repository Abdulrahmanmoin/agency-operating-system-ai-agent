"""Central registry of the user-invocable agents + the capabilities menu.

The capabilities offer (shown when a user uploads a transcript with no task) is generated
*from each agent's own* `name` / `role` / `responsibility` / `goal` attributes — there is no
separate hardcoded list to keep in sync. Add an agent module here and it appears in the menu.
"""

from dataclasses import dataclass

from agents import (
    clarification,
    clickup,
    planning,
    proposal,
    requirement,
    risk,
    task_generation,
    transcription,
    validator,
)
from agents.base import BaseAgent

# Ordered list of capability agents (Manager is the orchestrator, not a capability).
# Order = the natural left-to-right reading order of the menu.
# NOTE: the Executor agent (agents/executor.py) is intentionally NOT registered — its job was to
# save the package to the SERVER's disk, which a web user can't reach (the web UI downloads each
# artifact on demand instead). The module is kept dormant so it can be re-added here if a CLI/
# server-side bundle + audit-log/run-metrics deliverable is needed again.
_CAPABILITY_AGENTS: list[BaseAgent] = [
    transcription.run,
    requirement.run,
    clarification.run,
    planning.run,
    task_generation.run,
    risk.run,
    proposal.run,
    validator.run,
    clickup.run,
]

# name -> agent instance, for dispatch lookups elsewhere.
AGENTS: dict[str, BaseAgent] = {a.name: a for a in _CAPABILITY_AGENTS}


@dataclass(frozen=True)
class Capability:
    name: str  # internal agent key, e.g. "task_generation"
    display_name: str  # human label, e.g. "Task Generation"
    role: str
    responsibility: str
    goal: str


def _display_name(name: str) -> str:
    return name.replace("_", " ").title()


def capabilities() -> list[Capability]:
    """Structured capability list derived live from agent metadata."""
    return [
        Capability(
            name=a.name,
            display_name=_display_name(a.name),
            role=a.role,
            responsibility=a.responsibility,
            goal=a.goal,
        )
        for a in _CAPABILITY_AGENTS
    ]


def capabilities_text(input_kind: str = "some material") -> str:
    """Render the capabilities offer message shown on a task-less upload."""
    import prompts

    return prompts.render(
        "system/capabilities.j2",
        capabilities=capabilities(),
        input_kind=input_kind,
    )
