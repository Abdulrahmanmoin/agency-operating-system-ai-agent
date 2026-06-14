"""ValidatorAgent — score the package against a rubric, approve it, or bounce work back.

Validator is the final step of a full pipeline (the Executor that once followed it on approval has
been removed — the web UI downloads each artifact on demand instead). On approval the queue simply
drains to `finalize`; on rejection it re-queues one target agent then itself, up to a retry cap.
"""

from pydantic import BaseModel, Field

from agents.base import BaseAgent
from config import settings
from graph.routing import KNOWN_AGENTS
from graph.state import AgencyState, RiskList, TaskList, ValidationReport
from llm import ainvoke_structured, get_chat_model

# Agents the validator may send work back to.
VALIDATABLE_TARGETS = ["requirement", "planning", "task_generation", "risk", "proposal"]


class ValidationDraft(BaseModel):
    """Fixed-field LLM output (reliable structured output), mapped to ValidationReport."""

    approved: bool = Field(description="True only if the package is consistent, complete, client-ready.")
    consistency: float = Field(description="0-10: internal consistency across requirements/plan/tasks/proposal.")
    completeness: float = Field(description="0-10: are all requirements and services covered downstream?")
    clarity: float = Field(description="0-10: clarity and client-readiness of the proposal.")
    feedback: str = Field(description="Concise summary of issues found, or confirmation if approved.")
    target_agent: str | None = Field(
        default=None, description="If not approved, the single agent whose output most needs revision."
    )


class ValidatorAgent(BaseAgent):
    name = "validator"
    role = "QA reviewer"
    responsibility = "Check consistency, duplicates, logical correctness, missing deliverables."
    goal = "Approve only when every rubric dimension passes; else send back to a specific agent."

    async def reason(self, state: AgencyState) -> str:
        return (
            f"Cross-checking requirements ↔ plan ↔ {len(state.tasks)} task(s) ↔ "
            f"{len(state.risks)} risk(s) ↔ proposal for consistency, completeness, and clarity; "
            "will approve or route the weakest output back for revision."
        )

    async def act(self, state: AgencyState, reasoning: str) -> ValidationReport:
        import prompts

        if state.proposal is None:
            return ValidationReport(
                approved=False,
                scores={},
                feedback="No proposal to validate.",
                target_agent="proposal" if state.plan is not None else None,
            )

        system = (
            f"You are the {self.role}. {self.responsibility} Goal: {self.goal} "
            "Be a fair, pragmatic reviewer: approve a solid, client-ready DRAFT and reject only "
            "for material defects (a requested service missing, an internal contradiction, or "
            "empty/placeholder content) — not for wanting more detail or polish. If not approved, "
            f"set target_agent to exactly one of: {', '.join(VALIDATABLE_TARGETS)}."
        )
        user = prompts.render(
            "tasks/validate.j2",
            requirements_json=(
                state.requirements.model_dump_json(indent=2) if state.requirements else "null"
            ),
            plan_json=(state.plan.model_dump_json(indent=2) if state.plan else "null"),
            tasks_json=TaskList(tasks=state.tasks).model_dump_json(indent=2),
            risks_json=RiskList(risks=state.risks).model_dump_json(indent=2),
            proposal_json=state.proposal.model_dump_json(indent=2),
        )

        model = get_chat_model("validator", temperature=0.0).with_structured_output(ValidationDraft)
        draft: ValidationDraft = await ainvoke_structured(
            model,
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        target = draft.target_agent if (not draft.approved and draft.target_agent in KNOWN_AGENTS) else None
        return ValidationReport(
            approved=draft.approved,
            scores={
                "consistency": draft.consistency,
                "completeness": draft.completeness,
                "clarity": draft.clarity,
            },
            feedback=draft.feedback,
            target_agent=target,
        )

    def merge(self, state: AgencyState, output: ValidationReport) -> AgencyState:
        state.validation_report = output
        if output.approved:
            return state  # approved; queue drains to finalize

        attempts = state.attempt_count.get("validation", 0)
        target = output.target_agent
        if target in KNOWN_AGENTS and attempts < settings.max_validator_retries:
            # Bounce back: re-run the target agent, then re-validate, preserving any agents queued
            # after validator until it approves.
            state.attempt_count["validation"] = attempts + 1
            following = [a for a in state.dispatch_queue[1:] if a not in {target, "validator"}]
            state.dispatch_queue = [target, "validator", *following]
            state.scratch["_queue_overridden"] = True
        else:
            # Out of retries (or no valid target) → stop, skip remaining work, escalate to user.
            state.dispatch_queue = []
            state.scratch["_queue_overridden"] = True
            state.last_assistant_message = (
                f"The deliverables didn't pass quality validation after {attempts} revision(s). "
                f"Key issues: {output.feedback}"
            )
        return state


run = ValidatorAgent()
