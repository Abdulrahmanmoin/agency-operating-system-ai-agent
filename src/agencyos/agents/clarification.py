"""ClarificationAgent — detect gaps and pause graph for HITL input."""

from agencyos.agents.base import BaseAgent
from agencyos.graph.state import AgencyState, Clarification, ClarificationSeverity


class ClarificationAgent(BaseAgent):
    name = "clarification"
    role = "Gap finder"
    responsibility = "Detect vague, missing, or contradictory requirements."
    goal = "Reach a complete, unambiguous requirement spec before planning."

    async def reason(self, state: AgencyState) -> str:
        return "Inspecting requirements for vague/missing/contradictory items; will pause for HITL if any are critical."

    async def act(self, state: AgencyState, reasoning: str) -> list[Clarification]:
        # TODO: rubric_checker + contradiction_detector
        raise NotImplementedError("ClarificationAgent.act not yet implemented")

    def merge(self, state: AgencyState, output: list[Clarification]) -> AgencyState:
        state.clarifications = output
        # Pause if any unanswered critical clarifications remain
        state.paused_for_input = any(
            c.user_answer is None and c.severity == ClarificationSeverity.CRITICAL
            for c in output
        )
        return state


run = ClarificationAgent()
