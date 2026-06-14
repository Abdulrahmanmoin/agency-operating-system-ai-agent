"""ProposalAgent — synthesize requirements + plan + tasks + risks into a client-facing proposal."""

from agents.base import BaseAgent
from graph.state import AgencyState, Proposal, RiskList, TaskList
from llm import ainvoke_structured, get_chat_model


class ProposalAgent(BaseAgent):
    name = "proposal"
    role = "Client communicator"
    responsibility = "Draft proposal, project summary, client-ready report, meeting recap."
    goal = "Client-facing docs that read like a senior account manager wrote them."

    async def reason(self, state: AgencyState) -> str:
        have = [
            name
            for name, present in [
                ("requirements", state.requirements is not None),
                ("plan", state.plan is not None),
                (f"{len(state.tasks)} tasks", bool(state.tasks)),
                (f"{len(state.risks)} risks", bool(state.risks)),
            ]
            if present
        ]
        return (
            f"Synthesizing {', '.join(have) or 'limited inputs'} into a client-facing proposal: "
            "executive summary, scope, timeline, pricing, and next steps. Risks will be framed "
            "constructively as considerations, not a raw risk list."
        )

    async def act(self, state: AgencyState, reasoning: str) -> Proposal:
        import prompts

        if state.requirements is None and state.plan is None:
            return Proposal(
                executive_summary="Insufficient information to draft a proposal.",
                scope="",
                timeline="",
                pricing="",
                next_steps="Gather requirements and a project plan first.",
            )

        system = (
            f"You are the {self.role}. {self.responsibility} Goal: {self.goal} "
            "Write in a confident, client-ready voice. Ground everything in the inputs; do not "
            "invent figures. Frame risks as constructive considerations, never as alarm. "
            "Each section (scope, timeline, pricing, next_steps) must be a single prose string "
            "(markdown allowed), never a nested object or list."
        )
        user = prompts.render(
            "tasks/draft_proposal.j2",
            requirements_json=(
                state.requirements.model_dump_json(indent=2) if state.requirements else "null"
            ),
            plan_json=(state.plan.model_dump_json(indent=2) if state.plan else "null"),
            tasks_json=TaskList(tasks=state.tasks).model_dump_json(indent=2),
            risks_json=RiskList(risks=state.risks).model_dump_json(indent=2),
        ) + self.revision_note(state)

        model = get_chat_model("specialist", temperature=0.3).with_structured_output(Proposal)
        return await ainvoke_structured(
            model,
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )

    def merge(self, state: AgencyState, output: Proposal) -> AgencyState:
        state.proposal = output
        return state


run = ProposalAgent()
