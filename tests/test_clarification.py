"""Tests for the ClarificationAgent: LLM gap detection + HITL resolution."""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from agencyos.agents.clarification import ClarificationAgent, GapAnalysis, GapItem
from agencyos.graph.builder import build_graph
from agencyos.graph.state import AgencyState, ClarificationSeverity, Intent, Requirements


class _Model:
    """Returns a fixed result regardless of schema."""

    def __init__(self, result):
        self._result = result

    def with_structured_output(self, _schema, **_kwargs):
        return self

    async def ainvoke(self, _messages):
        return self._result


class _SchemaModel:
    """Returns a different result per requested schema (for detect vs apply)."""

    def __init__(self, by_schema):
        self._by_schema = by_schema
        self._schema = None

    def with_structured_output(self, schema, **_kwargs):
        self._schema = schema
        return self

    async def ainvoke(self, _messages):
        return self._by_schema[self._schema]


def _patch_intent(monkeypatch, intent: Intent) -> None:
    async def fake_classify(self, state):  # noqa: ANN001
        return Intent(**intent.model_dump())

    monkeypatch.setattr("agencyos.agents.manager.ManagerAgent.classify_intent", fake_classify)


# ─── unit: detection without interrupts ───────────────────────────────


async def test_no_gaps_returns_empty(monkeypatch):
    monkeypatch.setattr(
        "agencyos.agents.clarification.get_chat_model", lambda *a, **k: _Model(GapAnalysis(items=[]))
    )
    agent = ClarificationAgent()
    reqs = Requirements(client_goals=["g"], target_audience="SMBs")
    out = await agent.act(AgencyState(user_id="u", requirements=reqs), reasoning="r")
    assert out["clarifications"] == []
    assert out["requirements"] is reqs


async def test_noncritical_gap_does_not_interrupt(monkeypatch):
    gaps = GapAnalysis(
        items=[GapItem(field="services", issue="a bit vague", severity="major", question="Which channels?")]
    )
    monkeypatch.setattr("agencyos.agents.clarification.get_chat_model", lambda *a, **k: _Model(gaps))
    agent = ClarificationAgent()
    reqs = Requirements(client_goals=["g"])
    out = await agent.act(AgencyState(user_id="u", requirements=reqs), reasoning="r")
    assert len(out["clarifications"]) == 1
    assert out["clarifications"][0].severity == ClarificationSeverity.MAJOR
    assert out["requirements"] is reqs  # unchanged; no HITL


# ─── graph: critical gap → interrupt → resume → requirements updated ──


async def test_clarification_hitl_via_graph(monkeypatch):
    gaps = GapAnalysis(
        items=[
            GapItem(
                field="target_audience",
                issue="not specified",
                severity="critical",
                question="Who is the target audience?",
            )
        ]
    )
    updated = Requirements(client_goals=["g"], target_audience="enterprise buyers")
    monkeypatch.setattr(
        "agencyos.agents.clarification.get_chat_model",
        lambda *a, **k: _SchemaModel({GapAnalysis: gaps, Requirements: updated}),
    )
    _patch_intent(monkeypatch, Intent(agents=["clarification"]))

    app = build_graph().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t-clar-hitl"}}
    state = AgencyState(
        user_id="u",
        requirements=Requirements(client_goals=["g"]),  # no target_audience
        last_user_message="check for gaps",
    )
    out = await app.ainvoke(state, cfg)
    assert "__interrupt__" in out
    assert out["__interrupt__"][0].value["kind"] == "clarification"
    assert "target audience" in out["__interrupt__"][0].value["question"].lower()

    final = await app.ainvoke(Command(resume="enterprise buyers"), cfg)
    assert final["requirements"].target_audience == "enterprise buyers"
    criticals = [c for c in final["clarifications"] if c.severity == ClarificationSeverity.CRITICAL]
    assert criticals and criticals[0].user_answer == "enterprise buyers"
