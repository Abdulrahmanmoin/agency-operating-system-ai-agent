"""Tests for the ExecutorAgent — real artifact writing + run summary + zip."""

import json
import zipfile

from agencyos.agents.executor import ExecutorAgent
from agencyos.graph.state import (
    AgencyState,
    AuditEntry,
    AuditPhase,
    Milestone,
    Plan,
    Proposal,
    Requirements,
    Risk,
    RiskSeverity,
    Task,
    ValidationReport,
)


def _full_state() -> AgencyState:
    return AgencyState(
        user_id="u",
        requirements=Requirements(client_goals=["launch"], services=["e-commerce"], budget="$40k"),
        plan=Plan(summary="phased", phases=[Milestone(name="Phase 1", description="Foundation")]),
        tasks=[Task(id="T1", title="Build", description="d", priority=1, milestone="Phase 1")],
        risks=[Risk(title="Budget", description="tight", severity=RiskSeverity.HIGH, mitigation="scope")],
        proposal=Proposal(
            executive_summary="We will deliver.",
            scope="e-commerce",
            timeline="mid-October",
            pricing="$40,000",
            next_steps="kick off",
        ),
        validation_report=ValidationReport(approved=True, scores={"consistency": 9.0}, feedback="ok"),
        audit_log=[
            AuditEntry(agent="requirement", phase=AuditPhase.ACT, content="..."),
            AuditEntry(agent="risk", phase=AuditPhase.TOOL, content="tavily_search: ..."),
            AuditEntry(agent="proposal", phase=AuditPhase.ACT, content="..."),
        ],
    )


async def test_executor_writes_all_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr("agencyos.config.settings.output_dir", tmp_path)

    agent = ExecutorAgent()
    state = _full_state()
    out = await agent.act(state, reasoning="r")

    folder = tmp_path / str(state.conversation_id)
    for name in (
        "requirements.json",
        "plan.json",
        "tasks.json",
        "risks.json",
        "proposal.md",
        "audit_log.json",
        "run_summary.json",
    ):
        assert (folder / name).exists(), f"missing {name}"

    # proposal.md is human-readable
    assert "# Project Proposal" in (folder / "proposal.md").read_text(encoding="utf-8")

    # run_summary reflects the audit log
    summary = json.loads((folder / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["total_agent_calls"] == 2  # two ACT entries
    assert summary["total_tool_calls"] == 1  # one TOOL entry
    assert summary["validator_scores"] == {"consistency": 9.0}
    assert summary["output_path"]

    # zip bundle exists and contains the proposal
    zip_path = tmp_path / f"{state.conversation_id}.zip"
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as zf:
        names = [n.split("/")[-1] for n in zf.namelist()]
    assert "proposal.md" in names

    # merge writes the summary onto state
    merged = agent.merge(state, out)
    assert merged.run_summary is not None
    assert merged.run_summary.output_path


async def test_executor_skips_absent_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr("agencyos.config.settings.output_dir", tmp_path)

    agent = ExecutorAgent()
    state = AgencyState(user_id="u")  # nothing produced
    await agent.act(state, reasoning="r")

    folder = tmp_path / str(state.conversation_id)
    assert (folder / "run_summary.json").exists()  # always written
    assert (folder / "audit_log.json").exists()
    assert not (folder / "requirements.json").exists()
    assert not (folder / "proposal.md").exists()
