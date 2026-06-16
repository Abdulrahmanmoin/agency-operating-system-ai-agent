"""Tests for the Progress Report agent: branch↔ticket matching, the per-dev/% rollup, the read-only
ClickUp/GitHub REST parsers, and the graph integration — all offline (no real HTTP, no MCP)."""

from langgraph.checkpoint.memory import MemorySaver

from agents.progress_report import ProgressReportAgent
from graph.builder import build_graph
from graph.state import AgencyState, ClickUpTicket, Intent
from tools.github import (
    TicketProgress,
    _branch_refs_ticket,
    match_tickets,
    render_report,
)


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

    monkeypatch.setattr("agents.manager.ManagerAgent.classify_intent", fake_classify)


# ─── branch ↔ ticket matching (pure) ──────────────────────────────────


def test_branch_refs_ticket_matches_prefixed_and_bare_and_path_forms():
    assert _branch_refs_ticket("CU-86abc123-login", "86abc123")
    assert _branch_refs_ticket("feature/CU-86abc123", "86abc123")
    assert _branch_refs_ticket("86abc123-fix", "86abc123")  # bare id fallback
    assert _branch_refs_ticket("CU-86ABC123", "86abc123")  # case-insensitive
    assert not _branch_refs_ticket("main", "86abc123")
    assert not _branch_refs_ticket("CU-86abc123", "")  # no id → no match


def test_match_tickets_derives_status_and_assignee():
    tickets = [
        {"id": "111", "name": "Login", "assignees": ["Abdul"]},
        {"id": "222", "name": "Signup", "assignees": ["Sara"]},
        {"id": "333", "name": "Profile", "assignees": ["Sara"]},
        {"id": "444", "name": "Orphan", "assignees": []},
    ]
    branches = [{"name": "feature/CU-333-profile"}]  # 333 has a branch but no PR
    pulls = [
        {"head_ref": "CU-111-login", "state": "closed", "merged": True, "url": "u111"},  # done
        {"head_ref": "CU-222-signup", "state": "open", "merged": False, "url": "u222"},  # in progress
    ]
    out = {p.ticket_id: p for p in match_tickets(tickets, branches, pulls)}

    assert out["111"].status == "done" and out["111"].assignee == "Abdul" and out["111"].pr_url == "u111"
    assert out["222"].status == "in_progress" and out["222"].pr_url == "u222"
    assert out["333"].status == "in_progress" and out["333"].branch == "feature/CU-333-profile"
    assert out["333"].pr_url is None
    assert out["444"].status == "not_started" and out["444"].assignee == "Unassigned"


def test_render_report_rollup_and_finished_callout():
    items = [
        TicketProgress("1", "Login", "Abdul", "done", pr_url="u1"),
        TicketProgress("2", "Cart", "Abdul", "done", pr_url="u2"),
        TicketProgress("3", "Signup", "Sara", "in_progress", branch="CU-3"),
        TicketProgress("4", "Profile", "Sara", "not_started"),
    ]
    md = render_report(items)
    assert "50% complete" in md  # 2 of 4 done
    assert "2/4 tickets done" in md and "2 remaining" in md
    assert "**Abdul**" in md and "✅ all 2 ticket(s) done" in md
    assert "**Sara**" in md and "0/2 done (1 in progress, 1 not started)" in md
    # the "dev1 finished before dev2" callout the PM cares about
    assert "Abdul finished all assigned tickets" in md
    assert "Sara still has open work" in md


def test_render_report_empty():
    assert "no ClickUp tickets" in render_report([])


# ─── read-only REST parsers (mocked httpx) ────────────────────────────


def _mock_httpx(monkeypatch, payload: dict):
    import httpx

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return payload

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None, params=None):
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)


async def test_list_tasks_parses(monkeypatch):
    from config import settings
    from tools import clickup_mcp

    monkeypatch.setattr(settings, "clickup_api_key", "pk_test")
    monkeypatch.setattr(settings, "clickup_team_id", "team1")
    monkeypatch.setattr(settings, "clickup_list_id", "list1")
    _mock_httpx(
        monkeypatch,
        {
            "tasks": [
                {
                    "id": "86abc",
                    "name": "Login",
                    "assignees": [{"id": 1, "username": "Abdul"}],
                    "status": {"status": "in progress"},
                }
            ]
        },
    )
    tasks = await clickup_mcp.list_tasks()
    assert tasks == [
        {"id": "86abc", "name": "Login", "assignees": ["Abdul"], "status": "in progress"}
    ]


async def test_list_tasks_empty_when_no_list(monkeypatch):
    from config import settings
    from tools import clickup_mcp

    monkeypatch.setattr(settings, "clickup_api_key", "pk_test")
    monkeypatch.setattr(settings, "clickup_team_id", "team1")
    monkeypatch.setattr(settings, "clickup_list_id", None)
    assert await clickup_mcp.list_tasks() == []


async def test_list_pulls_parses_merged_and_open(monkeypatch):
    from config import settings
    from tools import github

    monkeypatch.setattr(settings, "github_token", "ghp_x")
    monkeypatch.setattr(settings, "github_repo", "acme/app")
    # The pulls endpoint returns a JSON *array*, so mock json() to return a list directly.
    import httpx

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return [
                {
                    "head": {"ref": "CU-1-login"},
                    "user": {"login": "abdul"},
                    "state": "closed",
                    "merged_at": "2026-06-01T00:00:00Z",
                    "html_url": "https://github.com/acme/app/pull/1",
                    "title": "Login",
                },
                {
                    "head": {"ref": "CU-2-signup"},
                    "user": {"login": "sara"},
                    "state": "open",
                    "merged_at": None,
                    "html_url": "https://github.com/acme/app/pull/2",
                    "title": "Signup",
                },
            ]

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None, params=None):
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    pulls = await github.list_pulls()
    assert pulls[0]["merged"] is True and pulls[0]["head_ref"] == "CU-1-login"
    assert pulls[1]["merged"] is False and pulls[1]["state"] == "open"


async def test_list_branches_empty_when_unconfigured(monkeypatch):
    from config import settings
    from tools import github

    monkeypatch.setattr(settings, "github_token", None)
    assert await github.list_branches() == []
    assert await github.list_pulls() == []


# ─── agent behaviour ──────────────────────────────────────────────────


async def test_act_reports_when_github_not_configured(monkeypatch):
    monkeypatch.setattr("agents.progress_report.github_configured", lambda: False)
    agent = ProgressReportAgent()
    out = await agent.act(AgencyState(user_id="u"), "")
    assert "GITHUB_TOKEN" in out["message"] and "report" not in out


async def test_act_falls_back_to_conversation_tickets(monkeypatch):
    """No live ClickUp list, but tickets were created this conversation → still report on them."""
    monkeypatch.setattr("agents.progress_report.github_configured", lambda: True)

    async def no_tasks():
        return []

    async def some_branches():
        return [{"name": "CU-abc-login"}]

    async def no_pulls():
        return []

    monkeypatch.setattr("agents.progress_report.list_tasks", no_tasks)
    monkeypatch.setattr("agents.progress_report.list_branches", some_branches)
    monkeypatch.setattr("agents.progress_report.list_pulls", no_pulls)

    agent = ProgressReportAgent()
    state = AgencyState(user_id="u", clickup_tickets=[ClickUpTicket(id="abc", name="Login page")])
    out = await agent.act(state, "")
    assert "Login page" in out["report"]
    assert "in progress" in out["report"]  # branch exists, no PR → in progress


# ─── graph integration ────────────────────────────────────────────────


async def test_graph_routes_to_progress_report(monkeypatch):
    _patch_intent(monkeypatch, Intent(agents=["progress_report"]))
    monkeypatch.setattr("agents.progress_report.github_configured", lambda: True)

    async def fake_tasks():
        return [
            {"id": "1", "name": "Login", "assignees": ["Abdul"]},
            {"id": "2", "name": "Signup", "assignees": ["Sara"]},
        ]

    async def fake_branches():
        return [{"name": "CU-2-signup"}]

    async def fake_pulls():
        return [{"head_ref": "CU-1-login", "state": "closed", "merged": True, "url": "u1"}]

    monkeypatch.setattr("agents.progress_report.list_tasks", fake_tasks)
    monkeypatch.setattr("agents.progress_report.list_branches", fake_branches)
    monkeypatch.setattr("agents.progress_report.list_pulls", fake_pulls)

    app = _compile()
    state = AgencyState(user_id="u", last_user_message="give me a progress report for the PM")
    out = await app.ainvoke(state, _cfg("t-pr"))

    assert "__interrupt__" not in out  # read-only → no HITL
    report = out["progress_report"]
    assert report is not None and report == out["last_assistant_message"]
    assert "50% complete" in report  # 1 of 2 done
    assert "Abdul" in report and "Sara" in report
