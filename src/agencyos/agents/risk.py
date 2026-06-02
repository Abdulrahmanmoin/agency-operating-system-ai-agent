"""RiskAnalysisAgent — detect deadline / budget / scope risks."""

from agencyos.agents.base import BaseAgent
from agencyos.graph.state import AgencyState, Risk


class RiskAnalysisAgent(BaseAgent):
    name = "risk"
    role = "Risk auditor"
    responsibility = "Detect unrealistic deadlines, unclear scope, budget mismatches, bottlenecks."
    goal = "Surface every material risk with severity and mitigation before client sign-off."

    async def reason(self, state: AgencyState) -> str:
        return "Scanning plan, tasks, and requirements for risks; may verify benchmarks via web search."

    async def act(self, state: AgencyState, reasoning: str) -> list[Risk]:
        raise NotImplementedError("RiskAnalysisAgent.act not yet implemented")

    def merge(self, state: AgencyState, output: list[Risk]) -> AgencyState:
        state.risks = output
        return state


run = RiskAnalysisAgent()
