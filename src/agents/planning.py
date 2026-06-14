"""PlanningAgent — turn structured requirements into a phased roadmap via Groq."""

from agents.base import BaseAgent
from graph.state import AgencyState, Plan
from llm import ainvoke_structured, get_chat_model


class PlanningAgent(BaseAgent):
    name = "planning"
    role = "Strategist"
    responsibility = "Build roadmap, milestones, phases, execution strategy."
    goal = "A phased plan that maps every requirement to a milestone."

    async def reason(self, state: AgencyState) -> str:
        reqs = state.requirements
        n_goals = len(reqs.client_goals) if reqs else 0
        n_services = len(reqs.services) if reqs else 0
        return (
            f"Have requirements with {n_goals} goal(s) and {n_services} service(s). Will design a "
            "phased roadmap whose milestones cover every service and goal, respecting the stated "
            "deadline, budget, and constraints."
        )

    async def act(self, state: AgencyState, reasoning: str) -> Plan:
        import prompts

        reqs = state.requirements
        if reqs is None:
            # Planning normally runs after requirement; guard defensively.
            return Plan(summary="No requirements available to plan from.")

        system = (
            f"You are the {self.role}. {self.responsibility} Goal: {self.goal} "
            "Ground every milestone in the requirements provided; do not invent scope, budget, "
            "or dates that aren't supported by them."
        )
        user = prompts.render(
            "tasks/build_plan.j2",
            requirements_json=reqs.model_dump_json(indent=2),
        ) + self.revision_note(state)

        model = get_chat_model("specialist", temperature=0.2).with_structured_output(Plan)
        return await ainvoke_structured(
            model,
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )

    def merge(self, state: AgencyState, output: Plan) -> AgencyState:
        state.plan = output
        return state


run = PlanningAgent()
