"""ValidatorAgent — gate before Executor."""

from agencyos.agents.base import BaseAgent
from agencyos.graph.state import AgencyState, ValidationReport


class ValidatorAgent(BaseAgent):
    name = "validator"
    role = "QA reviewer"
    responsibility = "Check consistency, duplicates, logical correctness, missing deliverables."
    goal = "Approve only when every rubric dimension passes; else send back to a specific agent."

    async def reason(self, state: AgencyState) -> str:
        return "Cross-checking requirements ↔ plan ↔ tasks ↔ proposal for gaps and inconsistencies."

    async def act(self, state: AgencyState, reasoning: str) -> ValidationReport:
        raise NotImplementedError("ValidatorAgent.act not yet implemented")

    def merge(self, state: AgencyState, output: ValidationReport) -> AgencyState:
        state.validation_report = output
        return state


run = ValidatorAgent()
