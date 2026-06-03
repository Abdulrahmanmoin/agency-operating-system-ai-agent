"""ProposalAgent — draft client-facing documents."""

from agencyos.agents.base import BaseAgent
from agencyos.graph.state import AgencyState, Proposal


class ProposalAgent(BaseAgent):
    name = "proposal"
    role = "Client communicator"
    responsibility = "Draft proposal, project summary, client-ready report, meeting recap."
    goal = "Client-facing docs that read like a senior account manager wrote them."

    async def reason(self, state: AgencyState) -> str:
        return "Synthesizing requirements + plan + tasks into client-facing proposal sections."

    async def act(self, state: AgencyState, reasoning: str) -> Proposal:
        # PLACEHOLDER: real client-facing drafting lands later.
        return Proposal(
            executive_summary="(placeholder) executive summary",
            scope="(placeholder) scope",
            timeline="(placeholder) timeline",
            pricing="(placeholder) pricing",
            next_steps="(placeholder) next steps",
        )

    def merge(self, state: AgencyState, output: Proposal) -> AgencyState:
        state.proposal = output
        return state


run = ProposalAgent()
