"""TaskGenerationAgent — Jira-style decomposition of the plan."""

from agencyos.agents.base import BaseAgent
from agencyos.graph.state import AgencyState, Task


class TaskGenerationAgent(BaseAgent):
    name = "task_generation"
    role = "Project decomposer"
    responsibility = "Generate tasks, subtasks, priorities, dependencies."
    goal = "Every milestone decomposed into actionable, dependency-ordered tasks."

    async def reason(self, state: AgencyState) -> str:
        return "Decomposing each milestone into ordered tasks with explicit dependencies."

    async def act(self, state: AgencyState, reasoning: str) -> list[Task]:
        raise NotImplementedError("TaskGenerationAgent.act not yet implemented")

    def merge(self, state: AgencyState, output: list[Task]) -> AgencyState:
        state.tasks = output
        return state


run = TaskGenerationAgent()
