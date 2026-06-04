"""Tests for the orchestrator's turn driver (offline: MemorySaver + mocked intent)."""

from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver

from agencyos.graph.builder import build_graph
from agencyos.graph.state import AgencyState, Intent
from agencyos.orchestrator import drive_turn


def _app():
    return build_graph().compile(checkpointer=MemorySaver())


def _patch_intent(monkeypatch, intent: Intent) -> None:
    async def fake_classify(self, state):  # noqa: ANN001
        i = Intent(**intent.model_dump())
        i.agents = list(intent.agents)
        return i

    monkeypatch.setattr("agencyos.agents.manager.ManagerAgent.classify_intent", fake_classify)


async def test_first_taskless_turn_returns_capabilities_message():
    app = _app()
    cid = uuid4()
    seed = AgencyState(conversation_id=cid, user_id="u", notes_path="m.txt")
    res = await drive_turn(app, cid, user_message=None, seed=seed)
    assert res.kind == "message"
    assert res.awaiting_input is False
    assert "What would you like me to do?" in res.message


async def test_continuing_turn_runs_agent(monkeypatch):
    _patch_intent(monkeypatch, Intent(agents=["requirement"]))
    app = _app()
    cid = uuid4()
    seed = AgencyState(conversation_id=cid, user_id="u", transcript="brief")
    # first turn: no task -> capabilities
    await drive_turn(app, cid, user_message=None, seed=seed)
    # second turn: a real instruction on the SAME thread
    res = await drive_turn(app, cid, user_message="extract requirements")
    assert res.kind == "message"
    # the message now shows the actual extracted requirements, not just a status line
    assert "Requirements" in res.message
    assert "(stub goal)" in res.message


async def test_confirmation_interrupt_then_resume(monkeypatch):
    _patch_intent(monkeypatch, Intent(agents=["proposal"]))
    app = _app()
    cid = uuid4()
    seed = AgencyState(conversation_id=cid, user_id="u", transcript="brief")
    res = await drive_turn(app, cid, user_message="draft a proposal", seed=seed)
    assert res.kind == "awaiting_confirmation"
    assert res.awaiting_input is True
    assert "requirement" in res.question and "planning" in res.question

    # resume with "yes"
    final = await drive_turn(app, cid, user_message="yes")
    assert final.kind == "message"
    assert "Proposal" in final.message  # the drafted proposal is shown back to the user
