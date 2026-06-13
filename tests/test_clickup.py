"""Tests for ClickUp ticket creation: drafting, the HITL confirm/cancel loop, the source-material
gate exemption, and the MCP result parsing — all offline (the MCP server is never spawned)."""

from contextlib import asynccontextmanager

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from agencyos.agents.clickup import ClickUpAgent, ClickUpChange, ClickUpPlan, _is_cancel
from agencyos.graph.builder import build_graph
from agencyos.graph.state import AgencyState, ClickUpTicket, ClickUpTicketDraft, Intent, Task


# ─── helpers ──────────────────────────────────────────────────────────


def _compile():
    return build_graph().compile(checkpointer=MemorySaver())


def _cfg(tid: str) -> dict:
    return {"configurable": {"thread_id": tid}}


def _patch_intent(monkeypatch, intent: Intent) -> None:
    async def fake_classify(self, state):  # noqa: ANN001
        i = Intent(**intent.model_dump())
        i.agents = list(intent.agents)
        return i

    monkeypatch.setattr("agencyos.agents.manager.ManagerAgent.classify_intent", fake_classify)


def _stub_draft(monkeypatch, drafts: list[ClickUpTicketDraft]) -> None:
    """Make the ClickUp agent's LLM return exactly `drafts`."""
    plan = ClickUpPlan(tickets=drafts)

    class _Structured:
        async def ainvoke(self, _messages):
            return plan

    class _Model:
        def with_structured_output(self, _schema, **_kwargs):
            return _Structured()

    monkeypatch.setattr("agencyos.agents.clickup.get_chat_model", lambda *a, **k: _Model())


def _stub_llm_sequence(monkeypatch, plans: list[ClickUpPlan]) -> None:
    """Return `plans` across successive LLM calls (e.g. _draft then _apply_details)."""
    state = {"i": 0}

    class _Structured:
        async def ainvoke(self, _messages):
            plan = plans[min(state["i"], len(plans) - 1)]
            state["i"] += 1
            return plan

    class _Model:
        def with_structured_output(self, _schema, **_kwargs):
            return _Structured()

    monkeypatch.setattr("agencyos.agents.clickup.get_chat_model", lambda *a, **k: _Model())


def _stub_plan(monkeypatch, plan: ClickUpPlan) -> None:
    """Make every ClickUp LLM call (draft + apply) return `plan`."""

    class _Structured:
        async def ainvoke(self, _messages):
            return plan

    class _Model:
        def with_structured_output(self, _schema, **_kwargs):
            return _Structured()

    monkeypatch.setattr("agencyos.agents.clickup.get_chat_model", lambda *a, **k: _Model())


def _stub_by_schema(monkeypatch, by_schema: dict) -> None:
    """Return a result keyed by the structured-output schema — robust across interrupt re-runs
    (the node re-runs _draft each resume, so a positional sequence stub would drift)."""

    class _Structured:
        def __init__(self, result):
            self._result = result

        async def ainvoke(self, _messages):
            return self._result

    class _Model:
        def with_structured_output(self, schema, **_kwargs):
            return _Structured(by_schema[schema])

    monkeypatch.setattr("agencyos.agents.clickup.get_chat_model", lambda *a, **k: _Model())


def _stub_members(monkeypatch, members: list[dict] | None = None) -> None:
    async def fake_members():
        return members or []

    monkeypatch.setattr("agencyos.agents.clickup.list_workspace_members", fake_members)


# ─── unit: helpers + drafting ─────────────────────────────────────────


def test_is_cancel():
    assert _is_cancel("no") and _is_cancel("cancel") and _is_cancel("stop") and _is_cancel("no thanks")
    assert _is_cancel(False)
    assert not _is_cancel("yes") and not _is_cancel("due Friday, high, assign to me")
    assert not _is_cancel("just create them")


async def test_draft_from_tasks(monkeypatch):
    _stub_draft(
        monkeypatch,
        [ClickUpTicketDraft(name="A", description="a"), ClickUpTicketDraft(name="B")],
    )
    agent = ClickUpAgent()
    state = AgencyState(
        user_id="u",
        last_user_message="push the tasks to clickup",
        tasks=[Task(id="T1", title="A", description="a", priority=1, milestone="P1")],
    )
    plan = await agent._draft(state)
    assert [d.name for d in plan.tickets] == ["A", "B"]


# ─── MCP tool module (no subprocess) ──────────────────────────────────


def test_extract_ticket_parses_json():
    from agencyos.tools.clickup_mcp import _extract_ticket

    raw = '{"id": "x1", "name": "Real", "url": "https://app.clickup.com/t/x1", "list": {"id": "L9"}}'
    t = _extract_ticket(raw, ClickUpTicketDraft(name="fallback"), "L1")
    assert t is not None
    assert t.id == "x1" and t.url == "https://app.clickup.com/t/x1" and t.list_id == "L9"


def test_extract_ticket_returns_none_without_a_task():
    """A non-task reply (workspace prompt, license notice, plain text) is NOT a created ticket."""
    from agencyos.tools.clickup_mcp import _extract_ticket

    draft = ClickUpTicketDraft(name="x")
    assert _extract_ticket("⚠️ Multiple Workspaces Detected ...", draft, "L1") is None
    assert _extract_ticket('{"note": "no id here"}', draft, "L1") is None
    assert _extract_ticket("not json at all", draft, "L1") is None


def test_extract_ticket_from_content_list_ignores_sponsor_text():
    from agencyos.tools.clickup_mcp import _extract_ticket

    raw = ['{"id": "86z", "name": "T", "url": "https://app.clickup.com/t/86z"}', "♥ Support this project"]
    t = _extract_ticket(raw, ClickUpTicketDraft(name="x"), "L1")
    assert t is not None and t.id == "86z"


def _fake_tools_with_create(return_value):
    tool = type("_T", (), {"ainvoke": lambda self, args: _async(return_value)})()

    @asynccontextmanager
    async def fake_tools():
        yield {"create_task": tool}

    return fake_tools


async def _async(value):
    return value


async def test_create_via_mcp_raises_on_non_task_reply(monkeypatch):
    """The fix for the 'says created but nothing exists' bug: no task id → raise, not false success."""
    from agencyos.tools import clickup_mcp

    monkeypatch.setattr(
        clickup_mcp, "clickup_tools", _fake_tools_with_create("⚠️ Multiple Workspaces Detected")
    )
    with pytest.raises(RuntimeError, match="did not create"):
        await clickup_mcp._create_tickets_via_mcp([ClickUpTicketDraft(name="x")], "L1")


async def test_create_via_mcp_success(monkeypatch):
    from agencyos.tools import clickup_mcp

    payload = ['{"id": "86abc", "name": "x", "url": "https://app.clickup.com/t/86abc", "list": {"id": "L1"}}', "♥ sponsor"]
    monkeypatch.setattr(clickup_mcp, "clickup_tools", _fake_tools_with_create(payload))
    out = await clickup_mcp._create_tickets_via_mcp([ClickUpTicketDraft(name="x")], "L1")
    assert len(out) == 1 and out[0].id == "86abc" and out[0].url.endswith("86abc")


def test_find_create_tool():
    from agencyos.tools.clickup_mcp import _find_create_tool

    sentinel = object()
    assert _find_create_tool({"create_task": sentinel}) is sentinel
    assert _find_create_tool({"clickup_create_task_v2": sentinel}) is sentinel
    with pytest.raises(RuntimeError):
        _find_create_tool({"list_spaces": object()})


async def test_create_tickets_requires_config(monkeypatch):
    from agencyos.tools import clickup_mcp

    monkeypatch.setattr(clickup_mcp, "clickup_configured", lambda: False)
    with pytest.raises(RuntimeError, match="isn't configured"):
        await clickup_mcp.create_tickets([ClickUpTicketDraft(name="x")])


async def test_create_via_mcp_includes_due_date_and_assignees_only_when_set(monkeypatch):
    from agencyos.tools import clickup_mcp

    seen = {}

    class _Tool:
        async def ainvoke(self, args):
            seen.update(args)
            return '{"id": "1", "name": "x", "url": "u"}'

    @asynccontextmanager
    async def fake_tools():
        yield {"create_task": _Tool()}

    monkeypatch.setattr(clickup_mcp, "clickup_tools", fake_tools)

    # no due_date / assignees → keys absent
    await clickup_mcp._create_tickets_via_mcp([ClickUpTicketDraft(name="x")], "L1")
    assert "dueDate" not in seen and "assignees" not in seen

    # with them → keys present
    seen.clear()
    await clickup_mcp._create_tickets_via_mcp(
        [ClickUpTicketDraft(name="x", due_date="next Friday", assignees=["111"])], "L1"
    )
    assert seen["dueDate"] == "next Friday" and seen["assignees"] == ["111"]


# ─── workspace member lookup (read-only REST, mocked) ─────────────────


async def test_list_workspace_members_parses(monkeypatch):
    import httpx

    from agencyos.config import settings
    from agencyos.tools import clickup_mcp

    monkeypatch.setattr(settings, "clickup_api_key", "pk_test")
    monkeypatch.setattr(settings, "clickup_team_id", "90182781700")

    team_json = {
        "teams": [
            {
                "id": "90182781700",
                "members": [{"user": {"id": 111, "username": "Abdul", "email": "a@b.com"}}],
            },
            {"id": "999", "members": [{"user": {"id": 222, "username": "Other"}}]},
        ]
    }

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return team_json

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None):
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    members = await clickup_mcp.list_workspace_members()
    assert members == [{"id": "111", "username": "Abdul", "email": "a@b.com"}]  # only the matching team


async def test_list_workspace_members_empty_when_unconfigured(monkeypatch):
    from agencyos.tools import clickup_mcp

    monkeypatch.setattr(clickup_mcp, "clickup_configured", lambda: False)
    assert await clickup_mcp.list_workspace_members() == []


async def test_apply_details_resolves_assignee(monkeypatch):
    enriched = ClickUpPlan(
        tickets=[ClickUpTicketDraft(name="Call client", priority=2, due_date="Friday", assignees=["111"])]
    )
    _stub_draft(monkeypatch, enriched.tickets)  # the apply LLM returns the enriched plan

    agent = ClickUpAgent()
    out = await agent._apply_details(
        [ClickUpTicketDraft(name="Call client", priority=3)],
        [{"id": "111", "username": "Abdul", "email": "a@b.com"}],
        "due Friday, high, assign to Abdul",
    )
    assert out[0].assignees == ["111"] and out[0].priority == 2 and out[0].due_date == "Friday"


# ─── graph integration: confirm / cancel / gate ──────────────────────


async def test_confirm_creates_tickets(monkeypatch):
    _patch_intent(monkeypatch, Intent(agents=["clickup"]))
    _stub_draft(monkeypatch, [ClickUpTicketDraft(name="Call client", description="Fri", priority=2)])
    _stub_members(monkeypatch, [])
    monkeypatch.setattr("agencyos.agents.clickup.clickup_configured", lambda: True)

    async def fake_create(drafts, list_id=None):  # noqa: ANN001
        return [ClickUpTicket(id="abc", name="Call client", url="https://app.clickup.com/t/abc")]

    monkeypatch.setattr("agencyos.agents.clickup.create_tickets", fake_create)

    app = _compile()
    state = AgencyState(user_id="u", last_user_message="create a ticket to call the client Friday")
    out = await app.ainvoke(state, _cfg("t-cu-yes"))

    # paused to gather details BEFORE creating anything — the prompt asks for due date/priority/assignee
    assert "__interrupt__" in out
    q = out["__interrupt__"][0].value
    assert q["kind"] == "confirmation"
    assert "Call client" in q["question"]
    assert "due date" in q["question"].lower() and "assignee" in q["question"].lower()

    final = await app.ainvoke(Command(resume="just create them"), _cfg("t-cu-yes"))
    assert [t.name for t in final["clickup_tickets"]] == ["Call client"]
    assert "Created 1 ClickUp ticket" in final["last_assistant_message"]


async def test_cancel_creates_nothing(monkeypatch):
    _patch_intent(monkeypatch, Intent(agents=["clickup"]))
    _stub_draft(monkeypatch, [ClickUpTicketDraft(name="Call client")])
    _stub_members(monkeypatch, [])
    monkeypatch.setattr("agencyos.agents.clickup.clickup_configured", lambda: True)

    async def boom(drafts, list_id=None):  # noqa: ANN001
        raise AssertionError("must not create tickets when the user declines")

    monkeypatch.setattr("agencyos.agents.clickup.create_tickets", boom)

    app = _compile()
    state = AgencyState(user_id="u", last_user_message="make a clickup ticket")
    await app.ainvoke(state, _cfg("t-cu-no"))
    final = await app.ainvoke(Command(resume="cancel"), _cfg("t-cu-no"))

    assert final["clickup_tickets"] == []
    assert "won't create" in final["last_assistant_message"]


async def test_detail_answer_enriches_create_args(monkeypatch):
    """The HITL reply (due date / priority / assignee) must reach create_tickets on the drafts."""
    _patch_intent(monkeypatch, Intent(agents=["clickup"]))
    _stub_llm_sequence(
        monkeypatch,
        [
            ClickUpPlan(tickets=[ClickUpTicketDraft(name="Call client", priority=3)]),  # _draft
            ClickUpPlan(  # _apply_details → enriched
                tickets=[
                    ClickUpTicketDraft(
                        name="Call client", priority=2, due_date="next Friday", assignees=["111"]
                    )
                ]
            ),
        ],
    )
    _stub_members(monkeypatch, [{"id": "111", "username": "Abdul", "email": "a@b.com"}])
    monkeypatch.setattr("agencyos.agents.clickup.clickup_configured", lambda: True)

    captured = {}

    async def fake_create(drafts, list_id=None):  # noqa: ANN001
        captured["drafts"] = list(drafts)
        return [ClickUpTicket(id="z1", name=drafts[0].name, url="https://app.clickup.com/t/z1")]

    monkeypatch.setattr("agencyos.agents.clickup.create_tickets", fake_create)

    app = _compile()
    state = AgencyState(user_id="u", last_user_message="create a ticket to call the client")
    out = await app.ainvoke(state, _cfg("t-cu-detail"))
    assert "Abdul" in out["__interrupt__"][0].value["question"]  # member offered as assignee

    final = await app.ainvoke(Command(resume="due next Friday, high priority, assign to me"), _cfg("t-cu-detail"))
    d = captured["drafts"][0]
    assert d.due_date == "next Friday" and d.priority == 2 and d.assignees == ["111"]
    assert "Created 1 ClickUp ticket" in final["last_assistant_message"]


async def test_skip_questions_creates_without_interrupt(monkeypatch):
    """When the user declines/provides details, the agent creates immediately — no detail prompt."""
    _patch_intent(monkeypatch, Intent(agents=["clickup"]))
    _stub_plan(
        monkeypatch,
        ClickUpPlan(tickets=[ClickUpTicketDraft(name="Call client")], skip_questions=True),
    )
    _stub_members(monkeypatch, [])
    monkeypatch.setattr("agencyos.agents.clickup.clickup_configured", lambda: True)

    created = {}

    async def fake_create(drafts, list_id=None):  # noqa: ANN001
        created["n"] = len(drafts)
        return [ClickUpTicket(id="z", name="Call client", url="https://app.clickup.com/t/z")]

    monkeypatch.setattr("agencyos.agents.clickup.create_tickets", fake_create)

    app = _compile()
    state = AgencyState(user_id="u", last_user_message="create a ticket to call client, no details needed")
    out = await app.ainvoke(state, _cfg("t-cu-skip"))

    assert "__interrupt__" not in out  # NO details prompt
    assert created["n"] == 1
    assert [t.name for t in out["clickup_tickets"]] == ["Call client"]


async def test_needs_title_asks_for_title_then_creates(monkeypatch):
    """No subject → ask 'what should the ticket be about?' instead of inventing a title."""
    _patch_intent(monkeypatch, Intent(agents=["clickup"]))
    _stub_llm_sequence(
        monkeypatch,
        [
            ClickUpPlan(tickets=[], needs_title=True),  # _draft: no subject given
            ClickUpPlan(  # re-draft from the title reply (+ _apply_details reuse)
                tickets=[ClickUpTicketDraft(name="Call the client")], skip_questions=True
            ),
        ],
    )
    _stub_members(monkeypatch, [])
    monkeypatch.setattr("agencyos.agents.clickup.clickup_configured", lambda: True)

    async def fake_create(drafts, list_id=None):  # noqa: ANN001
        return [ClickUpTicket(id="t1", name=drafts[0].name, url="https://app.clickup.com/t/t1")]

    monkeypatch.setattr("agencyos.agents.clickup.create_tickets", fake_create)

    app = _compile()
    state = AgencyState(user_id="u", last_user_message="create a ticket but no due date priority and assignee")
    out = await app.ainvoke(state, _cfg("t-cu-title"))

    # asks for the TITLE (not due date/priority/assignee), and didn't fabricate one
    q = out["__interrupt__"][0].value["question"]
    assert "what should the clickup ticket be about" in q.lower()

    final = await app.ainvoke(Command(resume="Call the client"), _cfg("t-cu-title"))
    assert [t.name for t in final["clickup_tickets"]] == ["Call the client"]


async def test_update_intent_updates_most_recent_ticket(monkeypatch):
    """A follow-up referring to an existing ticket UPDATES it (no new ticket), using context from
    state.clickup_tickets — the fix for 'assign this ticket / set its due date' creating a dupe."""
    _patch_intent(monkeypatch, Intent(agents=["clickup"]))
    _stub_by_schema(
        monkeypatch,
        {
            ClickUpPlan: ClickUpPlan(action="update", target_ref="this"),
            ClickUpChange: ClickUpChange(assignees=["111"], due_date="18 June 2026"),
        },
    )
    _stub_members(monkeypatch, [{"id": "111", "username": "Abdul", "email": "a@b.com"}])
    monkeypatch.setattr("agencyos.agents.clickup.clickup_configured", lambda: True)

    captured = {}

    async def fake_update(task_id, name, *, new_name=None, priority=None, due_date=None, assignees=None):  # noqa: ANN001
        captured.update(task_id=task_id, due_date=due_date, assignees=assignees)
        return ClickUpTicket(id=task_id, name=name, url=f"https://app.clickup.com/t/{task_id}")

    monkeypatch.setattr("agencyos.agents.clickup.update_ticket", fake_update)

    app = _compile()
    state = AgencyState(
        user_id="u",
        clickup_tickets=[ClickUpTicket(id="abc", name="call to client", url="https://app.clickup.com/t/abc")],
        last_user_message="assign this ticket to me with due date of 18 june 2026",
    )
    out = await app.ainvoke(state, _cfg("t-cu-upd"))

    assert "__interrupt__" not in out  # updates straight away, no new-ticket prompt
    assert captured["task_id"] == "abc"  # the existing ticket, not a new one
    assert captured["assignees"] == ["111"] and captured["due_date"] == "18 June 2026"
    assert "Updated" in out["last_assistant_message"]
    assert len(out["clickup_tickets"]) == 1  # still one ticket, updated in place


async def test_update_with_no_existing_tickets_explains(monkeypatch):
    _patch_intent(monkeypatch, Intent(agents=["clickup"]))
    _stub_by_schema(monkeypatch, {ClickUpPlan: ClickUpPlan(action="update", target_ref="this")})

    app = _compile()
    state = AgencyState(user_id="u", last_user_message="assign this ticket to me")
    out = await app.ainvoke(state, _cfg("t-cu-upd-none"))

    assert "__interrupt__" not in out
    assert "nothing to update" in out["last_assistant_message"]


async def test_update_ambiguous_asks_which(monkeypatch):
    _patch_intent(monkeypatch, Intent(agents=["clickup"]))
    _stub_by_schema(
        monkeypatch,
        {
            ClickUpPlan: ClickUpPlan(action="update", target_ref="something unmatched"),
            ClickUpChange: ClickUpChange(priority=2),
        },
    )
    _stub_members(monkeypatch, [])
    monkeypatch.setattr("agencyos.agents.clickup.clickup_configured", lambda: True)

    captured = {}

    async def fake_update(task_id, name, *, new_name=None, priority=None, due_date=None, assignees=None):  # noqa: ANN001
        captured["task_id"] = task_id
        return ClickUpTicket(id=task_id, name=name)

    monkeypatch.setattr("agencyos.agents.clickup.update_ticket", fake_update)

    app = _compile()
    state = AgencyState(
        user_id="u",
        clickup_tickets=[
            ClickUpTicket(id="a", name="Alpha task"),
            ClickUpTicket(id="b", name="Beta task"),
        ],
        last_user_message="make that ticket high priority",
    )
    out = await app.ainvoke(state, _cfg("t-cu-upd-amb"))
    assert "Which ticket should I update" in out["__interrupt__"][0].value["question"]

    final = await app.ainvoke(Command(resume="Beta task"), _cfg("t-cu-upd-amb"))
    assert captured["task_id"] == "b"
    assert "Updated" in final["last_assistant_message"]


async def test_clickup_not_refused_without_material(monkeypatch):
    """The source-material gate must NOT block ClickUp — it works from a free-form request even
    with no notes/transcript/requirements."""
    _patch_intent(monkeypatch, Intent(agents=["clickup"]))
    _stub_draft(monkeypatch, [])  # nothing concrete to create

    app = _compile()
    state = AgencyState(user_id="u", last_user_message="push to clickup")
    out = await app.ainvoke(state, _cfg("t-cu-gate"))

    msg = out["last_assistant_message"] or ""
    assert "don't have any meeting data" not in msg  # NOT the source-material refusal
    assert "couldn't find anything" in msg  # the agent ran and found nothing to create
    assert "__interrupt__" not in out


async def test_unconfigured_clickup_explains_instead_of_creating(monkeypatch):
    _patch_intent(monkeypatch, Intent(agents=["clickup"]))
    _stub_draft(monkeypatch, [ClickUpTicketDraft(name="Ticket A")])
    monkeypatch.setattr("agencyos.agents.clickup.clickup_configured", lambda: False)

    app = _compile()
    state = AgencyState(user_id="u", last_user_message="create a ticket")
    out = await app.ainvoke(state, _cfg("t-cu-unconf"))

    assert "__interrupt__" not in out  # no confirmation when it can't act anyway
    assert "CLICKUP_API_KEY" in out["last_assistant_message"]
    assert out["clickup_tickets"] == []
