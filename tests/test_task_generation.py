"""Tests for the TaskGenerationAgent (LLM mocked, no network)."""

from agents.task_generation import TaskGenerationAgent
from graph.state import AgencyState, Milestone, Plan, Task, TaskList


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
    monkeypatch.setattr("agents.task_generation.get_chat_model", lambda *a, **k: model)


async def test_generates_tasks_from_plan(monkeypatch):
    result = TaskList(
        tasks=[
            Task(id="T1", title="Build site", description="d", priority=1, milestone="Phase 1"),
            Task(id="T2", title="Launch", description="d", priority=2, depends_on=["T1"], milestone="Phase 2"),
        ]
    )
    holder: dict = {}
    _patch_model(monkeypatch, result, holder)

    agent = TaskGenerationAgent()
    state = AgencyState(
        user_id="u",
        plan=Plan(summary="s", phases=[Milestone(name="Phase 1", description="Foundation")]),
    )
    out = await agent.act(state, reasoning="r")
    assert isinstance(out, TaskList)
    assert [t.id for t in out.tasks] == ["T1", "T2"]
    # merge writes the list onto state
    merged = agent.merge(state, out)
    assert len(merged.tasks) == 2
    assert merged.tasks[1].depends_on == ["T1"]
    # plan was serialized into the prompt
    assert "Foundation" in holder["model"].structured.captured_messages[-1]["content"]


async def test_no_plan_is_safe(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("LLM should not be called without a plan")

    monkeypatch.setattr("agents.task_generation.get_chat_model", _boom)

    agent = TaskGenerationAgent()
    out = await agent.act(AgencyState(user_id="u"), reasoning="r")
    assert isinstance(out, TaskList)
    assert out.tasks == []


async def test_reason_counts_milestones():
    agent = TaskGenerationAgent()
    state = AgencyState(
        user_id="u",
        plan=Plan(summary="s", phases=[Milestone(name="P1", description="d"), Milestone(name="P2", description="d")]),
    )
    reasoning = await agent.reason(state)
    assert "2 milestone(s)" in reasoning
