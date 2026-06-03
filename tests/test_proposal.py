"""Tests for the ProposalAgent (LLM mocked, no network)."""

from agencyos.agents.proposal import ProposalAgent
from agencyos.graph.state import (
    AgencyState,
    Milestone,
    Plan,
    Proposal,
    Requirements,
    Risk,
    RiskSeverity,
    Task,
)


class _FakeStructured:
    def __init__(self, result):
        self._result = result
        self.captured_messages = None

    async def ainvoke(self, messages):
        self.captured_messages = messages
        return self._result


class _FakeModel:
    def __init__(self, result):
        self.structured = _FakeStructured(result)

    def with_structured_output(self, _schema, **_kwargs):
        return self.structured


def _patch_model(monkeypatch, result, holder=None):
    model = _FakeModel(result)
    if holder is not None:
        holder["model"] = model
    monkeypatch.setattr("agencyos.agents.proposal.get_chat_model", lambda *a, **k: model)


async def test_proposal_synthesizes_all_inputs(monkeypatch):
    result = Proposal(
        executive_summary="We'll launch your DTC store.",
        scope="E-commerce + SEO",
        timeline="4 phases to mid-October",
        pricing="$40,000 engagement",
        next_steps="Sign off and kick off",
    )
    holder: dict = {}
    _patch_model(monkeypatch, result, holder)

    agent = ProposalAgent()
    state = AgencyState(
        user_id="u",
        requirements=Requirements(client_goals=["launch DTC store"], services=["e-commerce"], budget="$40k"),
        plan=Plan(summary="phased", phases=[Milestone(name="Phase 1", description="Foundation")]),
        tasks=[Task(id="T1", title="Build site", description="d", priority=1, milestone="Phase 1")],
        risks=[Risk(title="Budget", description="tight", severity=RiskSeverity.HIGH, mitigation="scope")],
    )
    out = await agent.act(state, reasoning="r")
    assert out.pricing == "$40,000 engagement"

    user_msg = holder["model"].structured.captured_messages[-1]["content"]
    # all four inputs are serialized into the prompt
    assert "launch DTC store" in user_msg
    assert "Phase 1" in user_msg
    assert "Build site" in user_msg
    assert "Budget" in user_msg


async def test_proposal_without_inputs_is_safe(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("LLM should not be called without requirements or plan")

    monkeypatch.setattr("agencyos.agents.proposal.get_chat_model", _boom)

    agent = ProposalAgent()
    out = await agent.act(AgencyState(user_id="u"), reasoning="r")
    assert isinstance(out, Proposal)
    assert "Insufficient information" in out.executive_summary


async def test_proposal_reason_lists_present_inputs():
    agent = ProposalAgent()
    state = AgencyState(
        user_id="u",
        requirements=Requirements(),
        plan=Plan(summary="s"),
    )
    reasoning = await agent.reason(state)
    assert "requirements" in reasoning and "plan" in reasoning
