"""RequirementAnalysisAgent — extract structured requirements from transcript/notes via Groq."""

from agencyos.agents.base import BaseAgent
from agencyos.graph.state import AgencyState, Requirements
from agencyos.llm import ainvoke_structured, get_chat_model


class RequirementAnalysisAgent(BaseAgent):
    name = "requirement"
    role = "Brief decoder"
    responsibility = "Extract client goals, services, deadlines, budget, constraints, priorities."
    goal = "Convert messy conversation into a typed Requirements object with high recall."

    async def reason(self, state: AgencyState) -> str:
        text = state.source_material()
        n = len(text) if text else 0
        return (
            f"Have {n} chars of source material. Will extract goals, services, deadline, budget, "
            "constraints, priorities, and target audience into the Requirements schema, leaving "
            "any unstated field empty rather than guessing."
        )

    async def act(self, state: AgencyState, reasoning: str) -> Requirements:
        from agencyos import prompts

        text = state.source_material()
        if not text or not text.strip():
            # Nothing to extract from — return an empty spec; clarification will catch gaps.
            return Requirements()

        system = (
            f"You are the {self.role}. {self.responsibility} Goal: {self.goal} "
            "Extract only what is genuinely present in the material; never fabricate details."
        )
        user = prompts.render("tasks/extract_requirements.j2", source=text) + self.revision_note(state)

        model = get_chat_model("specialist", temperature=0.0).with_structured_output(Requirements)
        return await ainvoke_structured(
            model,
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )

    def merge(self, state: AgencyState, output: Requirements) -> AgencyState:
        state.requirements = output
        return state


run = RequirementAnalysisAgent()
