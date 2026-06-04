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


async def test_regenerate_reruns_existing_agent(monkeypatch):
    from agencyos.graph.state import Milestone, Plan, Requirements

    _patch_intent(monkeypatch, Intent(agents=["planning"], regenerate=True))
    app = _compile()
    state = AgencyState(
        user_id="u",
        transcript="b",
        requirements=Requirements(client_goals=["g"]),
        plan=Plan(summary="OLD plan", phases=[Milestone(name="Old", description="old")]),
        last_user_message="regenerate the plan",
    )
    out = await app.ainvoke(state, _cfg("t-regen"))
    # planning actually re-ran (not just re-shown) and replaced the old plan
    assert "planning" in out["scratch"]["executed"]
    assert out["plan"].summary == "(stub plan)"


async def test_no_regenerate_reuses_cached_output(monkeypatch):
    from agencyos.graph.state import Milestone, Plan, Requirements

    _patch_intent(monkeypatch, Intent(agents=["planning"], regenerate=False))
    app = _compile()
    state = AgencyState(
        user_id="u",
        transcript="b",
        requirements=Requirements(client_goals=["g"]),
        plan=Plan(summary="OLD plan", phases=[Milestone(name="Old", description="old")]),
        last_user_message="show me the plan",
    )
    out = await app.ainvoke(state, _cfg("t-cache"))
    # planning did NOT re-run; the existing plan is shown unchanged
    assert "planning" not in out["scratch"].get("executed", [])
    assert out["plan"].summary == "OLD plan"


async def test_full_pipeline_runs_everything(monkeypatch):
    _patch_intent(monkeypatch, Intent(full_pipeline=True))
    app = _compile()
    state = AgencyState(user_id="u", transcript="brief", last_user_message="handle it end to end")
    # With clarification detecting no gaps (conftest stub), the pipeline runs straight through.
    out = await app.ainvoke(state, _cfg("t-full"))
    assert "__interrupt__" not in out
    assert out["proposal"] is not None
    assert out["validation_report"] is not None
    assert out["run_summary"] is not None
    # transcription is skipped (no audio); the rest of the pipeline ran in order
    assert out["scratch"]["executed"] == [
        "requirement",
        "clarification",
        "planning",
        "task_generation",
        "risk",
        "proposal",
        "validator",
        "executor",
    ]
