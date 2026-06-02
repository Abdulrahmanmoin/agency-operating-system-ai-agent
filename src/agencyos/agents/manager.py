"""ManagerAgent — orchestrator. See ARCHITECTURE.md §2."""

from agencyos.agents.base import BaseAgent
from agencyos.graph.state import AgencyState


class ManagerAgent(BaseAgent):
    name = "manager"
    role = "Chief of Staff"
    responsibility = "Route to specialists, handle validator feedback, decide completion."
    goal = "Deliver a validator-approved package with minimum retries."

    async def reason(self, state: AgencyState) -> str:
        # TODO: render prompts/system/manager.j2 + reasoning_rubric partial
        return f"Inspecting state; next routing decision will be made by manager_router."

    async def act(self, state: AgencyState, reasoning: str) -> dict:
        # Manager itself produces no payload — routing is handled by manager_router.
        return {"acknowledged": True}

    def merge(self, state: AgencyState, output: dict) -> AgencyState:
        return state


run = ManagerAgent()
