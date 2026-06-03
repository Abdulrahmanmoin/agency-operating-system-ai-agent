"""Integration tests for the conversational graph (offline: MemorySaver + mocked intent)."""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from agencyos.graph.builder import build_graph
from agencyos.graph.state import AgencyState, Intent


def _compile():
    return build_graph().compile(checkpointer=MemorySaver())


def _patch_intent(monkeypatch, intent: Intent) -> None:
    async def fake_classify(self, state):  # noqa: ANN001
        i = Intent(**intent.model_dump())
        i.agents = list(intent.agents)
        return i

    monkeypatch.setattr(
        "agencyos.agents.manager.ManagerAgent.classify_intent", fake_classify
    )


def _cfg(tid: str) -> dict:
    return {"configurable": {"thread_id": tid}}


async def test_capabilities_offer_on_taskless_first_turn():
    app = _compile()
    state = AgencyState(user_id="u", notes_path="meeting.txt")
    out = await app.ainvoke(state, _cfg("t-cap"))
    assert "What would you like me to do?" in out["last_assistant_message"]
    assert out["capabilities_offered"] is True
    assert "__interrupt__" not in out


async def test_single_agent_runs_only_that_agent(monkeypatch):
    _patch_intent(monkeypatch, Intent(agents=["requirement"]))
    app = _compile()
    state = AgencyState(user_id="u", transcript="we need a website", last_user_message="extract requirements")
    out = await app.ainvoke(state, _cfg("t-req"))
    assert out["requirements"] is not None
    assert out.get("plan") is None  # nothing else ran
    assert out["scratch"]["executed"] == ["requirement"]


async def test_missing_prereq_asks_then_runs_chain_on_yes(monkeypatch):
    _patch_intent(monkeypatch, Intent(agents=["proposal"]))
    app = _compile()
    state = AgencyState(user_id="u", transcript="brief", last_user_message="draft a proposal")
    out = await app.ainvoke(state, _cfg("t-prq"))
    # graph paused to ask about prerequisites
    assert "__interrupt__" in out
    q = out["__interrupt__"][0].value
    assert q["kind"] == "confirmation"
    assert q["prerequisites"] == ["requirement", "planning"]

    # user says yes -> requirement, planning, then proposal all run
    final = await app.ainvoke(Command(resume="yes"), _cfg("t-prq"))
    assert final["requirements"] is not None
    assert final["plan"] is not None
    assert final["proposal"] is not None
    assert final["scratch"]["executed"] == ["requirement", "planning", "proposal"]


async def test_missing_prereq_declined_runs_nothing(monkeypatch):
    _patch_intent(monkeypatch, Intent(agents=["proposal"]))
    app = _compile()
    state = AgencyState(user_id="u", transcript="brief", last_user_message="draft a proposal")
    await app.ainvoke(state, _cfg("t-no"))
    final = await app.ainvoke(Command(resume="no"), _cfg("t-no"))
    assert final.get("proposal") is None
    assert final.get("requirements") is None
    assert "won't run" in final["last_assistant_message"]


async def test_unmappable_request_asks_to_rephrase(monkeypatch):
    _patch_intent(monkeypatch, Intent(agents=[], full_pipeline=False))
    app = _compile()
    state = AgencyState(user_id="u", transcript="brief", last_user_message="what's the weather")
    out = await app.ainvoke(state, _cfg("t-unmap"))
    assert "rephrase" in out["last_assistant_message"]


async def test_clarification_pauses_for_missing_audience(monkeypatch):
    from agencyos.graph.state import Requirements

    _patch_intent(monkeypatch, Intent(agents=["clarification"]))
    app = _compile()
    state = AgencyState(
        user_id="u",
        transcript="b",
        requirements=Requirements(client_goals=["x"]),  # present, but no target_audience
        last_user_message="check for gaps",
    )
    out = await app.ainvoke(state, _cfg("t-clar"))
    assert "__interrupt__" in out
    assert out["__interrupt__"][0].value["kind"] == "clarification"
    assert out["__interrupt__"][0].value["field"] == "target_audience"

    final = await app.ainvoke(Command(resume="enterprise buyers"), _cfg("t-clar"))
    assert final["requirements"].target_audience == "enterprise buyers"
    assert final["clarifications"][0].user_answer == "enterprise buyers"


async def test_full_pipeline_runs_everything(monkeypatch):
    _patch_intent(monkeypatch, Intent(full_pipeline=True))
    app = _compile()
    state = AgencyState(user_id="u", transcript="brief", last_user_message="handle it end to end")
    out = await app.ainvoke(state, _cfg("t-full"))
    # pipeline pauses mid-way at the clarification HITL (missing target audience)
    assert "__interrupt__" in out
    assert out["__interrupt__"][0].value["kind"] == "clarification"

    final = await app.ainvoke(Command(resume="small businesses"), _cfg("t-full"))
    assert final["proposal"] is not None
    assert final["validation_report"] is not None
    assert final["run_summary"] is not None
    assert final["requirements"].target_audience == "small businesses"
    # transcription is skipped (no audio); the rest of the pipeline ran in order
    assert final["scratch"]["executed"] == [
        "requirement",
        "clarification",
        "planning",
        "task_generation",
        "risk",
        "proposal",
        "validator",
        "executor",
    ]
