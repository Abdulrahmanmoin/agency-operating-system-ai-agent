"""RequirementAnalysisAgent — extract structured requirements from transcript/notes."""

from agencyos.agents.base import BaseAgent
from agencyos.graph.state import AgencyState, Requirements


class RequirementAnalysisAgent(BaseAgent):
    name = "requirement"
    role = "Brief decoder"
    responsibility = "Extract client goals, services, deadlines, budget, constraints, priorities."
    goal = "Convert messy conversation into a typed Requirements object with high recall."

    async def reason(self, state: AgencyState) -> str:
        return "Reading transcript/notes; will extract goals, services, deadline, budget, constraints, priorities."

    async def act(self, state: AgencyState, reasoning: str) -> Requirements:
        # PLACEHOLDER: real extraction (Groq structured output over the transcript/notes)
        # lands in a later phase. For now emit a deterministic stub so routing is testable.
        source = state.transcript or state.notes_path or "(no source)"
        return Requirements(
            client_goals=["(placeholder) extracted from " + str(source)[:40]],
            services=["(placeholder service)"],
        )

    def merge(self, state: AgencyState, output: Requirements) -> AgencyState:
        state.requirements = output
        return state


run = RequirementAnalysisAgent()
