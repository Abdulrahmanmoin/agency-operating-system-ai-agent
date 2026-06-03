"""ClarificationAgent — LLM-driven gap/contradiction detection with HITL resolution.

Detects gaps in the requirements via the LLM. If any are *critical*, it pauses the graph once
(a single combined interrupt) to ask the user, then folds their answer back into the requirements
with a second LLM call. A single interrupt keeps the node idempotent across the resume re-run.
"""

from typing import Literal

from langgraph.types import interrupt
from pydantic import BaseModel, Field

from agencyos.agents.base import BaseAgent
from agencyos.graph.state import (
    AgencyState,
    Clarification,
    ClarificationSeverity,
    Requirements,
    _Payload,
)
from agencyos.llm import ainvoke_structured, get_chat_model


class GapItem(BaseModel):
    field: str = Field(description="Requirement field the gap concerns, or 'general'.")
    issue: str = Field(description="What is missing, ambiguous, or contradictory.")
    severity: Literal["critical", "major", "minor"]
    question: str = Field(description="The question to ask the client to resolve this gap.")


class GapAnalysis(_Payload):
    items: list[GapItem] | None = None


class ClarificationAgent(BaseAgent):
    name = "clarification"
    role = "Gap finder"
    responsibility = "Detect vague, missing, or contradictory requirements."
    goal = "Reach a complete, unambiguous requirement spec before planning."

    async def reason(self, state: AgencyState) -> str:
        return (
            "Analyzing the requirements for gaps, ambiguities, and contradictions; will pause to "
            "ask the user about any CRITICAL gaps before planning proceeds."
        )

    async def _detect(self, state: AgencyState) -> list[GapItem]:
        from agencyos import prompts

        reqs = state.requirements
        system = (
            f"You are the {self.role}. {self.responsibility} Goal: {self.goal} "
            "Only report genuine gaps grounded in the requirements; never invent issues."
        )
        user = prompts.render("tasks/detect_gaps.j2", requirements_json=reqs.model_dump_json(indent=2))
        model = get_chat_model("specialist", temperature=0.0).with_structured_output(GapAnalysis)
        analysis: GapAnalysis = await ainvoke_structured(
            model,
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return analysis.items

    async def _apply(self, reqs: Requirements, criticals: list[GapItem], answer: str) -> Requirements:
        from agencyos import prompts

        system = (
            "You update a requirements object using the client's answers. Fill only the fields the "
            "answer addresses; leave everything else exactly as-is. Never fabricate information."
        )
        user = prompts.render(
            "tasks/apply_clarifications.j2",
            requirements_json=reqs.model_dump_json(indent=2),
            questions="\n".join(f"- {c.question}" for c in criticals),
            answer=answer,
        )
        model = get_chat_model("specialist", temperature=0.0).with_structured_output(Requirements)
        return await ainvoke_structured(
            model,
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
        )

    async def act(self, state: AgencyState, reasoning: str) -> dict:
        reqs = state.requirements
        if reqs is None:
            return {"clarifications": [], "requirements": None}

        items = await self._detect(state)
        clarifications = [
            Clarification(field=i.field, issue=i.issue, severity=ClarificationSeverity(i.severity))
            for i in items
        ]
        criticals = [i for i in items if i.severity == "critical"]

        if not criticals:
            return {"clarifications": clarifications, "requirements": reqs}

        # Pause ONCE for all critical gaps, then fold the answer into the requirements.
        combined = "I need a bit more information before I can plan this:\n" + "\n".join(
            f"- {c.question}" for c in criticals
        )
        answer = interrupt(
            {"kind": "clarification", "question": combined, "fields": [c.field for c in criticals]}
        )
        updated = await self._apply(reqs, criticals, str(answer))
        for c in clarifications:
            if c.severity == ClarificationSeverity.CRITICAL:
                c.user_answer = str(answer)
        return {"clarifications": clarifications, "requirements": updated}

    def merge(self, state: AgencyState, output: dict) -> AgencyState:
        state.clarifications = output["clarifications"]
        if output["requirements"] is not None:
            state.requirements = output["requirements"]
        state.paused_for_input = any(
            c.user_answer is None and c.severity == ClarificationSeverity.CRITICAL
            for c in state.clarifications
        )
        return state


run = ClarificationAgent()
