"""Conditional routing functions used by Manager and Validator nodes."""

from agencyos.graph.state import AgencyState

# Order specialists run in on a clean path (no validator feedback).
SPECIALIST_ORDER = [
    "transcription",
    "requirement",
    "clarification",
    "planning",
    "task_generation",
    "risk",
    "proposal",
    "validator",
]


def manager_router(state: AgencyState) -> str:
    """Decide the next node from the Manager.

    Priority:
      1. If Validator rejected and we have retries left → re-dispatch named agent.
      2. If paused_for_input → END (CLI handles HITL pause).
      3. Otherwise advance through SPECIALIST_ORDER based on what's filled in state.
    """
    if state.paused_for_input:
        return "__end__"

    vr = state.validation_report
    if vr is not None and not vr.approved and vr.target_agent:
        from agencyos.config import settings

        attempts = state.attempt_count.get(vr.target_agent, 0)
        if attempts < settings.max_validator_retries:
            return vr.target_agent

    # Skip transcription if input is text
    if state.transcript is None and state.audio_path is None:
        # text input — synthesize transcript from notes upstream of requirement
        pass

    for step in SPECIALIST_ORDER:
        if not _step_done(state, step):
            # Skip transcription if not audio
            if step == "transcription" and state.audio_path is None:
                continue
            return step

    return "executor"


def _step_done(state: AgencyState, step: str) -> bool:
    match step:
        case "transcription":
            return state.transcript is not None
        case "requirement":
            return state.requirements is not None
        case "clarification":
            return state.clarifications is not None and not any(
                c.user_answer is None and c.severity.value == "critical"
                for c in state.clarifications
            )
        case "planning":
            return state.plan is not None
        case "task_generation":
            return bool(state.tasks)
        case "risk":
            return state.risks is not None
        case "proposal":
            return state.proposal is not None
        case "validator":
            return state.validation_report is not None and state.validation_report.approved
        case _:
            return False


def validator_router(state: AgencyState) -> str:
    """After Validator runs: approve → executor, reject → back to Manager."""
    vr = state.validation_report
    if vr is not None and vr.approved:
        return "executor"
    return "manager"
