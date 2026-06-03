"""ClarificationAgent — detect critical gaps and pause the graph for human input (HITL)."""

from langgraph.types import interrupt

from agencyos.agents.base import BaseAgent
from agencyos.graph.state import AgencyState, Clarification, ClarificationSeverity

# Requirement fields treated as critical: if missing, we must ask the user before proceeding.
# (Placeholder rule-based gap detection; real LLM-driven detection lands in a later phase.)
_CRITICAL_FIELDS: list[tuple[str, str]] = [
    ("target_audience", "Who is the target audience? It wasn't specified in the brief."),
]


class ClarificationAgent(BaseAgent):
    name = "clarification"
    role = "Gap finder"
    responsibility = "Detect vague, missing, or contradictory requirements."
    goal = "Reach a complete, unambiguous requirement spec before planning."

    async def reason(self, state: AgencyState) -> str:
        return (
            "Inspecting requirements for missing critical fields; "
            "will pause to ask the user (HITL) for anything essential that's absent."
        )

    async def act(self, state: AgencyState, reasoning: str) -> list[Clarification]:
        reqs = state.requirements
        clarifications: list[Clarification] = []
        if reqs is None:
            return clarifications

        for field_name, question in _CRITICAL_FIELDS:
            if getattr(reqs, field_name, None):
                continue
            # Pause the graph and ask the user. On resume, `answer` holds their reply.
            answer = interrupt({"kind": "clarification", "field": field_name, "question": question})
            value = str(answer).strip() if answer is not None else ""
            setattr(reqs, field_name, value)
            clarifications.append(
                Clarification(
                    field=field_name,
                    issue="missing",
                    severity=ClarificationSeverity.CRITICAL,
                    user_answer=value,
                )
            )
        return clarifications

    def merge(self, state: AgencyState, output: list[Clarification]) -> AgencyState:
        # `output` already carries user answers (gathered via interrupt in act()).
        state.clarifications = output
        state.paused_for_input = any(
            c.user_answer is None and c.severity == ClarificationSeverity.CRITICAL
            for c in output
        )
        return state


run = ClarificationAgent()
