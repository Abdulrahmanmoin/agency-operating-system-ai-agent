"""ExecutorAgent — write approved artifacts to disk, build the bundle, record run metrics."""

from datetime import datetime

from agents.base import BaseAgent
from graph.state import AgencyState, AuditPhase, RunSummary
from tools import file_io


class ExecutorAgent(BaseAgent):
    name = "executor"
    role = "Packager"
    responsibility = "Write approved artifacts to disk, build deliverable bundle, log metrics."
    goal = "A single outputs/<conversation_id>/ folder with every artifact and run_summary.json."

    async def reason(self, state: AgencyState) -> str:
        artifacts = [
            n
            for n, present in [
                ("requirements", state.requirements is not None),
                ("plan", state.plan is not None),
                ("tasks", bool(state.tasks)),
                ("risks", bool(state.risks)),
                ("proposal", state.proposal is not None),
            ]
            if present
        ]
        return (
            f"Packaging {', '.join(artifacts) or 'no artifacts'} to outputs/{state.conversation_id}/, "
            "writing a client-facing proposal.md and run_summary.json, then zipping the bundle."
        )

    async def act(self, state: AgencyState, reasoning: str) -> dict:
        cid = state.conversation_id

        # Structured artifacts (only those that exist).
        if state.requirements is not None:
            file_io.write_json(cid, "requirements.json", state.requirements.model_dump())
        if state.plan is not None:
            file_io.write_json(cid, "plan.json", state.plan.model_dump())
        if state.tasks:
            file_io.write_json(cid, "tasks.json", [t.model_dump() for t in state.tasks])
        if state.risks:
            file_io.write_json(cid, "risks.json", [r.model_dump() for r in state.risks])

        # Client-facing proposal as readable markdown.
        if state.proposal is not None:
            file_io.write_text(cid, "proposal.md", _proposal_markdown(state))

        # Full reasoning/decision trace (rubric: logging of agent actions & decisions).
        file_io.write_json(
            cid, "audit_log.json", [e.model_dump() for e in state.audit_log]
        )

        summary = _build_run_summary(state)
        output_path = str(file_io.conversation_dir(cid))
        summary.output_path = output_path
        file_io.write_json(cid, "run_summary.json", summary.model_dump())

        zip_path = file_io.zip_bundle(cid)
        return {"output_path": output_path, "zip_path": str(zip_path), "run_summary": summary}

    def merge(self, state: AgencyState, output: dict) -> AgencyState:
        state.run_summary = output["run_summary"]
        return state


def _proposal_markdown(state: AgencyState) -> str:
    p = state.proposal
    assert p is not None
    return (
        f"# Project Proposal\n\n"
        f"## Executive Summary\n{p.executive_summary}\n\n"
        f"## Scope\n{p.scope}\n\n"
        f"## Timeline\n{p.timeline}\n\n"
        f"## Pricing\n{p.pricing}\n\n"
        f"## Next Steps\n{p.next_steps}\n"
    )


def _build_run_summary(state: AgencyState) -> RunSummary:
    started = state.run_summary.started_at if state.run_summary else datetime.utcnow()
    agent_calls = sum(1 for e in state.audit_log if e.phase == AuditPhase.ACT)
    tool_calls = sum(1 for e in state.audit_log if e.phase == AuditPhase.TOOL)
    scores = state.validation_report.scores if state.validation_report else {}
    return RunSummary(
        started_at=started,
        ended_at=datetime.utcnow(),
        total_agent_calls=agent_calls,
        total_tool_calls=tool_calls,
        total_tokens=0,  # token accounting not yet wired
        retry_count=sum(state.attempt_count.values()),
        validator_scores=scores,
        incidents=[e.content for e in state.audit_log if e.phase == AuditPhase.ERROR],
    )


run = ExecutorAgent()
