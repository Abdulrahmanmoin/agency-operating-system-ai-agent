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
        # TODO: render prompts/tasks/extract_requirements.j2 + structured output via Groq
        raise NotImplementedError("RequirementAnalysisAgent.act not yet implemented")

    def merge(self, state: AgencyState, output: Requirements) -> AgencyState:
        state.requirements = output
        return state


run = RequirementAnalysisAgent()
