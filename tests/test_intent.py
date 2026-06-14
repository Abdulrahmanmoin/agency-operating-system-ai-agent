"""Tests for Manager intent classification + prerequisite resolution (LLM mocked, no network)."""

import pytest

from agents.manager import ManagerAgent
from graph.state import AgencyState, Intent, Requirements, Plan


class _FakeStructured:
    def __init__(self, intent: Intent):
        self._intent = intent

    async def ainvoke(self, _messages):
        return self._intent


class _FakeModel:
    def __init__(self, intent: Intent):
        self._intent = intent

    def with_structured_output(self, _schema):
        return _FakeStructured(self._intent)


def _patch_model(monkeypatch, intent: Intent) -> None:
    monkeypatch.setattr(
        "agents.manager.get_chat_model",
        lambda *a, **k: _FakeModel(intent),
    )


def _state(**kwargs) -> AgencyState:
    return AgencyState(user_id="tester", **kwargs)


@pytest.mark.asyncio
async def test_classify_intent_returns_mapped_agents(monkeypatch):
    _patch_model(monkeypatch, Intent(agents=["planning"], full_pipeline=False, rationale="r"))
    mgr = ManagerAgent()
    intent = await mgr.classify_intent(_state(last_user_message="make a plan"))
    assert intent.agents == ["planning"]
    assert intent.full_pipeline is False


@pytest.mark.asyncio
async def test_classify_intent_drops_hallucinated_agents(monkeypatch):
    _patch_model(monkeypatch, Intent(agents=["planning", "bogus_agent"], rationale="r"))
    mgr = ManagerAgent()
    intent = await mgr.classify_intent(_state(last_user_message="x"))
    assert intent.agents == ["planning"]


def test_resolve_prerequisites_flags_missing_chain():
    mgr = ManagerAgent()
    intent = Intent(agents=["proposal"])
    confirmation = mgr.resolve_prerequisites(_state(), intent)
    assert confirmation is not None
    assert confirmation.prerequisites == ["requirement", "planning"]
    assert "yes/no" in confirmation.question.lower()


def test_resolve_prerequisites_none_when_satisfied():
    mgr = ManagerAgent()
    s = _state(requirements=Requirements(), plan=Plan(summary="p"))
    assert mgr.resolve_prerequisites(s, Intent(agents=["proposal"])) is None


def test_resolve_prerequisites_none_for_full_pipeline():
    mgr = ManagerAgent()
    assert mgr.resolve_prerequisites(_state(), Intent(full_pipeline=True)) is None


def test_resolve_prerequisites_excludes_requested_from_prereqs():
    # user explicitly asked for requirement + proposal: requirement shouldn't be a "prereq"
    mgr = ManagerAgent()
    confirmation = mgr.resolve_prerequisites(_state(), Intent(agents=["requirement", "proposal"]))
    assert confirmation is not None
    assert "requirement" not in confirmation.prerequisites
    assert confirmation.prerequisites == ["planning"]
