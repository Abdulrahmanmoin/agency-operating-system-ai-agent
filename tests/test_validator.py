"""Tests for the ValidatorAgent: rubric scoring, executor gating, and bounce-back loop."""

from langgraph.checkpoint.memory import MemorySaver

from agencyos.agents.validator import ValidationDraft, ValidatorAgent
from agencyos.graph.builder import build_graph
from agencyos.graph.state import (
    AgencyState,
    Intent,
    Milestone,
    Plan,
    Proposal,
    Requirements,
    Task,
    ValidationReport,
)


class _FakeStructured:
    def __init__(self, result):
        self._result = result

    async def ainvoke(self, _messages):
        return self._result


class _FakeModel:
    def __init__(self, result):
        self._result = result

    def with_structured_output(self, _schema, **_kwargs):
        return _FakeStructured(self._result)


# ─── act(): draft → ValidationReport mapping ──────────────────────────


async def test_act_maps_draft_to_report(monkeypatch):
    draft = ValidationDraft(
        approved=False, consistency=5, completeness=6, clarity=4, feedback="weak", target_agent="proposal"
    )
    monkeypatch.setattr("agencyos.agents.validator.get_chat_model", lambda *a, **k: _FakeModel(draft))

    agent = ValidatorAgent()
    state = AgencyState(user_id="u", proposal=Proposal(executive_summary="x", scope="", timeline="", pricing="", next_steps=""))
    report = await agent.act(state, reasoning="r")
    assert report.approved is False
    assert report.scores == {"consistency": 5.0, "completeness": 6.0, "clarity": 4.0}
    assert report.target_agent == "proposal"


async def test_act_no_proposal_returns_unapproved(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("LLM should not be called without a proposal")

    monkeypatch.setattr("agencyos.agents.validator.get_chat_model", _boom)
    agent = ValidatorAgent()
    report = await agent.act(AgencyState(user_id="u", plan=Plan(summary="s")), reasoning="r")
    assert report.approved is False
    assert report.target_agent == "proposal"


# ─── merge(): gating + retry bookkeeping ──────────────────────────────


def test_merge_approved_leaves_queue():
    agent = ValidatorAgent()
    state = AgencyState(user_id="u", dispatch_queue=["validator", "executor"])
    agent.merge(state, ValidationReport(approved=True, feedback="ok"))
    assert state.dispatch_queue == ["validator", "executor"]
    assert "_queue_overridden" not in state.scratch


def test_merge_rejected_requeues_target_then_validator():
    agent = ValidatorAgent()
    state = AgencyState(user_id="u", dispatch_queue=["validator", "executor"])
    agent.merge(
        state, ValidationReport(approved=False, feedback="plan gap", target_agent="planning")
    )
    assert state.dispatch_queue == ["planning", "validator", "executor"]
    assert state.scratch["_queue_overridden"] is True
    assert state.attempt_count["validation"] == 1


def test_merge_rejected_exhausted_escalates():
    agent = ValidatorAgent()
    state = AgencyState(
        user_id="u", dispatch_queue=["validator", "executor"], attempt_count={"validation": 3}
    )
    agent.merge(
        state, ValidationReport(approved=False, feedback="still broken", target_agent="planning")
    )
    assert state.dispatch_queue == []  # executor skipped
    assert state.scratch["_queue_overridden"] is True
    assert "didn't pass quality validation" in state.last_assistant_message


# ─── graph integration: reject once, then approve, then execute ───────


def test_revision_note_only_when_targeted():
    from agencyos.agents.proposal import ProposalAgent
    from agencyos.agents.planning import PlanningAgent

    proposal = ProposalAgent()
    planning = PlanningAgent()
    state = AgencyState(
        user_id="u",
        validation_report=ValidationReport(
            approved=False, feedback="add specific timeline", target_agent="proposal"
        ),
    )
    # targeted agent gets the feedback; others get nothing
    assert "add specific timeline" in proposal.revision_note(state)
    assert planning.revision_note(state) == ""

    # once approved, nobody gets a revision note
    state.validation_report = ValidationReport(approved=True, feedback="ok")
    assert proposal.revision_note(state) == ""


class _SeqModel:
    """Returns a sequence of structured results across successive calls."""

    def __init__(self, results):
        self._results = list(results)
        self._i = 0

    def with_structured_output(self, _schema, **_kwargs):
        return self

    async def ainvoke(self, _messages):
        result = self._results[min(self._i, len(self._results) - 1)]
        self._i += 1
        return result


async def test_bounce_back_then_execute(monkeypatch):
    # validator rejects (→ proposal) on first pass, approves on second
    seq = _SeqModel(
        [
            ValidationDraft(approved=False, consistency=4, completeness=5, clarity=4, feedback="redo", target_agent="proposal"),
            ValidationDraft(approved=True, consistency=9, completeness=9, clarity=9, feedback="great"),
        ]
    )
    monkeypatch.setattr("agencyos.agents.validator.get_chat_model", lambda *a, **k: seq)

    async def fake_classify(self, state):  # noqa: ANN001
        return Intent(agents=["validator", "executor"], full_pipeline=False)

    monkeypatch.setattr("agencyos.agents.manager.ManagerAgent.classify_intent", fake_classify)

    app = build_graph().compile(checkpointer=MemorySaver())
    state = AgencyState(
        user_id="u",
        requirements=Requirements(client_goals=["g"], services=["s"], target_audience="SMBs"),
        plan=Plan(summary="s", phases=[Milestone(name="P1", description="d")]),
        tasks=[Task(id="T1", title="t", description="d", priority=1, milestone="P1")],
        proposal=Proposal(executive_summary="x", scope="s", timeline="t", pricing="p", next_steps="n"),
        last_user_message="validate and ship it",
    )
    out = await app.ainvoke(state, {"configurable": {"thread_id": "t-bounce"}})

    assert out["validation_report"].approved is True
    executed = out["scratch"]["executed"]
    assert executed.count("validator") == 2  # ran, bounced, ran again
    assert "proposal" in executed  # re-ran the target
    assert executed[-1] == "executor"  # gate opened, executor ran last
    assert out["run_summary"] is not None
