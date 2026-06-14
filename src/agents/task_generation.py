"""TaskGenerationAgent — decompose the plan's milestones into Jira-style tasks via Groq."""

from agents.base import BaseAgent
from graph.state import AgencyState, TaskList
from llm import ainvoke_structured, get_chat_model


class TaskGenerationAgent(BaseAgent):
    name = "task_generation"
    role = "Project decomposer"
    responsibility = "Generate tasks, subtasks, priorities, dependencies."
    goal = "Every milestone decomposed into actionable, dependency-ordered tasks."

    async def reason(self, state: AgencyState) -> str:
        n_phases = len(state.plan.phases) if state.plan else 0
        return (
            f"Have a plan with {n_phases} milestone(s). Will decompose each into actionable tasks "
            "with stable ids, priorities (1 = highest), and dependencies referencing earlier task ids."
        )

    async def act(self, state: AgencyState, reasoning: str) -> TaskList:
        import prompts

        plan = state.plan
        if plan is None:
            return TaskList()

        system = (
            f"You are the {self.role}. {self.responsibility} Goal: {self.goal} "
            "Derive tasks only from the plan; keep ids stable and dependencies acyclic."
        )
        user = prompts.render(
            "tasks/generate_tasks.j2", plan_json=plan.model_dump_json(indent=2)
        ) + self.revision_note(state)

        model = get_chat_model("specialist", temperature=0.2).with_structured_output(TaskList)
        return await ainvoke_structured(
            model,
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )

    def merge(self, state: AgencyState, output: TaskList) -> AgencyState:
        state.tasks = output.tasks
        return state


run = TaskGenerationAgent()
