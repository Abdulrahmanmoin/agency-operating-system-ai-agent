"""Tests for the PlanningAgent (LLM mocked, no network)."""

from agents.planning import PlanningAgent
from graph.state import AgencyState, Milestone, Plan, Requirements


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
    monkeypatch.setattr("agents.planning.get_chat_model", lambda *a, **k: model)


async def test_planning_builds_plan_from_requirements(monkeypatch):
    plan = Plan(
        summary="Phased DTC launch",
        phases=[
            Milestone(name="Phase 1 - Foundation", description="Build the store", deliverables=["site"]),
            Milestone(name="Phase 2 - Launch", description="Marketing", deliverables=["campaign"]),
        ],
    )
    holder: dict = {}
    _patch_model(monkeypatch, plan, holder)

    agent = PlanningAgent()
    state = AgencyState(
        user_id="u",
        requirements=Requirements(client_goals=["launch DTC store"], services=["e-commerce", "SEO"]),
    )
    out = await agent.act(state, reasoning="r")

    assert out.summary == "Phased DTC launch"
    assert len(out.phases) == 2
    # requirements were serialized into the prompt
    user_msg = holder["model"].structured.captured_messages[-1]["content"]
    assert "launch DTC store" in user_msg
    assert "e-commerce" in user_msg


async def test_planning_without_requirements_is_safe(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("LLM should not be called without requirements")

    monkeypatch.setattr("agents.planning.get_chat_model", _boom)

    agent = PlanningAgent()
    out = await agent.act(AgencyState(user_id="u"), reasoning="r")
    assert isinstance(out, Plan)
    assert "No requirements" in out.summary


async def test_planning_reason_counts_goals_and_services():
    agent = PlanningAgent()
    state = AgencyState(
        user_id="u",
        requirements=Requirements(client_goals=["a", "b"], services=["x"]),
    )
    reasoning = await agent.reason(state)
    assert "2 goal(s)" in reasoning and "1 service(s)" in reasoning
