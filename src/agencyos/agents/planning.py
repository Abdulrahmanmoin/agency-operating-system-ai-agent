"""PlanningAgent — build phased roadmap from requirements."""

from agencyos.agents.base import BaseAgent
from agencyos.graph.state import AgencyState, Plan


class PlanningAgent(BaseAgent):
    name = "planning"
    role = "Strategist"
    responsibility = "Build roadmap, milestones, phases, execution strategy."
    goal = "A phased plan that maps every requirement to a milestone."

    async def reason(self, state: AgencyState) -> str:
        return "Building phased plan from requirements; will consult past templates and industry benchmarks."

    async def act(self, state: AgencyState, reasoning: str) -> Plan:
        # PLACEHOLDER: real roadmap synthesis lands later.
        from agencyos.graph.state import Milestone

        return Plan(
            summary="(placeholder) phased plan derived from requirements",
            phases=[Milestone(name="Phase 1", description="(placeholder)")],
        )

    def merge(self, state: AgencyState, output: Plan) -> AgencyState:
        state.plan = output
        return state


run = PlanningAgent()
