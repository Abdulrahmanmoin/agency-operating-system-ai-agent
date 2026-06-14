"""Test bootstrap: provide stub env vars so `config.Settings` loads without real secrets.

These are set before any `agencyos` import so module-level `settings = Settings()` succeeds.
Real values come from `.env` in normal runs; tests never touch external services.
"""

import os
import tempfile

os.environ.setdefault("GROQ_API_KEY", "test-stub-key")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://stub:stub@localhost/stub")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql+psycopg://stub:stub@localhost/stub")
# Keep Executor artifacts out of the repo during tests.
os.environ.setdefault("OUTPUT_DIR", tempfile.mkdtemp(prefix="agencyos-test-out-"))

import pytest

from agents.clarification import GapAnalysis
from agents.clickup import ClickUpPlan
from agents.validator import ValidationDraft
from graph.state import (
    Milestone,
    Plan,
    Proposal,
    Requirements,
    Risk,
    RiskList,
    RiskSeverity,
    Task,
    TaskList,
)


def _fake_model_returning(result):
    """A stand-in chat model whose structured output always returns `result`."""

    class _FakeStructured:
        async def ainvoke(self, _messages):
            return result

    class _FakeModel:
        def with_structured_output(self, _schema, **_kwargs):
            return _FakeStructured()

    return _FakeModel()


# Canned outputs per real-LLM agent, so the full suite stays offline.
_STUB_OUTPUTS = {
    "agents.requirement.get_chat_model": Requirements(
        client_goals=["(stub goal)"], services=["(stub service)"]
    ),
    "agents.planning.get_chat_model": Plan(
        summary="(stub plan)", phases=[Milestone(name="Phase 1", description="(stub)")]
    ),
    "agents.task_generation.get_chat_model": TaskList(
        tasks=[Task(id="T1", title="(stub task)", description="(stub)", priority=1, milestone="Phase 1")]
    ),
    "agents.risk.get_chat_model": RiskList(
        risks=[
            Risk(
                title="(stub risk)",
                description="(stub)",
                severity=RiskSeverity.MEDIUM,
                mitigation="(stub)",
            )
        ]
    ),
    "agents.proposal.get_chat_model": Proposal(
        executive_summary="(stub summary)",
        scope="(stub scope)",
        timeline="(stub timeline)",
        pricing="(stub pricing)",
        next_steps="(stub next steps)",
    ),
    "agents.validator.get_chat_model": ValidationDraft(
        approved=True, consistency=9.0, completeness=9.0, clarity=9.0, feedback="ok"
    ),
    # Default: clarification finds no gaps, so the pipeline flows without interrupting.
    "agents.clarification.get_chat_model": GapAnalysis(items=[]),
    # Default: ClickUp drafts nothing, so unrelated tests never reach the MCP layer.
    "agents.clickup.get_chat_model": ClickUpPlan(tickets=[]),
}


@pytest.fixture(autouse=True)
def _stub_agent_llms(monkeypatch):
    """Keep the full suite offline: stub each real-LLM agent's Groq call with a canned result.

    Tests that need different behavior (e.g. test_requirement.py, test_planning.py) override
    these with their own monkeypatch in the test body, which runs after this fixture.
    """
    for target, result in _STUB_OUTPUTS.items():
        monkeypatch.setattr(target, lambda *a, _r=result, **k: _fake_model_returning(_r), raising=False)
