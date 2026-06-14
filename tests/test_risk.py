"""Tests for the RiskAnalysisAgent + Tavily integration (LLM and web search mocked)."""

from agents.risk import RiskAnalysisAgent
from graph.state import (
    AgencyState,
    AuditPhase,
    Milestone,
    Plan,
    Requirements,
    Risk,
    RiskList,
    RiskSeverity,
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
    monkeypatch.setattr("agents.risk.get_chat_model", lambda *a, **k: model)


def _state_with_plan(**extra) -> AgencyState:
    return AgencyState(
        user_id="u",
        requirements=Requirements(services=["e-commerce", "SEO"], deadline="mid-October", budget="$40k"),
        plan=Plan(summary="s", phases=[Milestone(name="Phase 1", description="d")]),
        **extra,
    )


async def test_risk_runs_without_tavily_when_no_key(monkeypatch):
    # No TAVILY_API_KEY in tests → web context skipped, but risk analysis still runs.
    monkeypatch.setattr("config.settings.tavily_api_key", None, raising=False)
    result = RiskList(risks=[Risk(title="Deadline", description="tight", severity=RiskSeverity.HIGH, mitigation="buffer")])
    holder: dict = {}
    _patch_model(monkeypatch, result, holder)

    agent = RiskAnalysisAgent()
    state = _state_with_plan()
    out = await agent.act(state, reasoning="r")

    assert [r.title for r in out.risks] == ["Deadline"]
    user_msg = holder["model"].structured.captured_messages[-1]["content"]
    assert "no external benchmark data" in user_msg
    # no tool-call audit entry since Tavily was skipped
    assert not [e for e in state.audit_log if e.phase == AuditPhase.TOOL]


async def test_risk_uses_tavily_when_configured(monkeypatch):
    monkeypatch.setattr("config.settings.tavily_api_key", "tvly-test", raising=False)

    async def fake_search(query, max_results=5, include_answer=True):  # noqa: ANN001
        return {
            "query": query,
            "answer": "Typical DTC build takes 4-6 months and $30-60k.",
            "results": [{"title": "Benchmark", "url": "http://x", "content": "details", "score": 0.9}],
        }

    monkeypatch.setattr("tools.web_search.tavily_search", fake_search)
    holder: dict = {}
    _patch_model(monkeypatch, RiskList(risks=[]), holder)

    agent = RiskAnalysisAgent()
    state = _state_with_plan()
    await agent.act(state, reasoning="r")

    user_msg = holder["model"].structured.captured_messages[-1]["content"]
    assert "Typical DTC build takes" in user_msg  # Tavily answer reached the prompt
    tool_entries = [e for e in state.audit_log if e.phase == AuditPhase.TOOL]
    assert len(tool_entries) == 1 and "tavily_search" in tool_entries[0].content


async def test_risk_tavily_failure_degrades_gracefully(monkeypatch):
    monkeypatch.setattr("config.settings.tavily_api_key", "tvly-test", raising=False)

    async def boom_search(*a, **k):
        raise RuntimeError("tavily down")

    monkeypatch.setattr("tools.web_search.tavily_search", boom_search)
    holder: dict = {}
    _patch_model(monkeypatch, RiskList(risks=[]), holder)

    agent = RiskAnalysisAgent()
    state = _state_with_plan()
    out = await agent.act(state, reasoning="r")  # must not raise
    assert isinstance(out, RiskList)
    user_msg = holder["model"].structured.captured_messages[-1]["content"]
    assert "no external benchmark data" in user_msg


async def test_risk_no_plan_or_tasks_is_safe(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("LLM should not be called with no plan and no tasks")

    monkeypatch.setattr("agents.risk.get_chat_model", _boom)

    agent = RiskAnalysisAgent()
    out = await agent.act(AgencyState(user_id="u"), reasoning="r")
    assert out.risks == []
