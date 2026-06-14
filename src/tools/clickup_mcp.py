"""ClickUp ticket creation via the Model Context Protocol (MCP).

Rather than calling ClickUp's REST API directly, we speak to a ClickUp **MCP server** (launched as
a stdio subprocess — by default the community `@taazkareem/clickup-mcp-server` via `npx`) and load
its tools as LangChain tools through `langchain-mcp-adapters`. The agent invokes the server's
create-task tool directly (deterministic args we control), so we get true MCP integration without
relying on the LLM to drive tool-calling.

The server reads `CLICKUP_API_KEY` + `CLICKUP_TEAM_ID` from its environment; tickets are created
inside a List (`CLICKUP_LIST_ID`). All of these come from settings/.env.
"""

import asyncio
import json
import os
import shlex
import sys
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

from config import settings
from graph.state import ClickUpTicket, ClickUpTicketDraft


def clickup_configured() -> bool:
    """True when the MCP server has enough credentials to talk to ClickUp."""
    return bool(settings.clickup_api_key and settings.clickup_team_id)


async def list_workspace_members() -> list[dict[str, Any]]:
    """Return the assignable members of the configured workspace as [{id, username, email}].

    This is the ONE place we hit ClickUp's REST API directly (read-only `GET /api/v2/team`): the
    pinned free MCP server has no reliable members tool, and we only need this to OFFER assignees in
    the HITL prompt — ticket creation still goes through MCP. Degrades to [] if unconfigured or on
    any error, so the agent simply proceeds without a member list.
    """
    if not clickup_configured():
        return []
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.clickup.com/api/v2/team",
                headers={"Authorization": settings.clickup_api_key or ""},
            )
            resp.raise_for_status()
            teams = resp.json().get("teams", [])
    except Exception:  # noqa: BLE001 — assignee discovery is best-effort
        return []

    team_id = str(settings.clickup_team_id)
    members: list[dict[str, Any]] = []
    seen: set[str] = set()
    for team in teams:
        if str(team.get("id")) != team_id:
            continue
        for entry in team.get("members", []):
            user = entry.get("user", entry)
            uid = user.get("id")
            if uid is None or str(uid) in seen:
                continue
            seen.add(str(uid))
            members.append(
                {
                    "id": str(uid),
                    "username": user.get("username") or user.get("email") or str(uid),
                    "email": user.get("email"),
                }
            )
    return members


def _server_params() -> Any:
    from mcp import StdioServerParameters

    # Merge the real environment (npx/node need PATH on Windows) with the ClickUp creds.
    env = {
        **os.environ,
        "CLICKUP_API_KEY": settings.clickup_api_key or "",
        "CLICKUP_TEAM_ID": settings.clickup_team_id or "",
    }
    return StdioServerParameters(
        command=settings.clickup_mcp_command,
        args=shlex.split(settings.clickup_mcp_args),
        env=env,
    )


@asynccontextmanager
async def clickup_tools() -> AsyncIterator[dict[str, Any]]:
    """Open ONE MCP stdio session and yield its tools keyed by name.

    The session (and the npx subprocess) lives for the duration of the `with` block, so a batch of
    ticket creations reuses a single connection instead of re-spawning per ticket.
    """
    from langchain_mcp_adapters.tools import load_mcp_tools
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await load_mcp_tools(session)
            yield {t.name: t for t in tools}


def _find_create_tool(tools: dict[str, Any]) -> Any:
    """Locate the server's create-task tool (names vary between MCP servers)."""
    for key in ("create_task", "createTask"):
        if key in tools:
            return tools[key]
    for name, tool in tools.items():
        lname = name.lower()
        if "create" in lname and "task" in lname:
            return tool
    raise RuntimeError(f"ClickUp MCP server exposes no create-task tool. Available: {list(tools)}")


def _find_update_tool(tools: dict[str, Any]) -> Any:
    """Locate the server's update-task tool."""
    for key in ("update_task", "updateTask"):
        if key in tools:
            return tools[key]
    for name, tool in tools.items():
        lname = name.lower()
        if "update" in lname and "task" in lname:
            return tool
    raise RuntimeError(f"ClickUp MCP server exposes no update-task tool. Available: {list(tools)}")


def _result_texts(raw: Any) -> list[str]:
    """Flatten an MCP tool result (str | list of str/content-blocks) into plain text strings."""
    items = list(raw) if isinstance(raw, (list, tuple)) else [raw]
    texts: list[str] = []
    for item in items:
        if isinstance(item, str):
            texts.append(item)
        elif isinstance(item, dict) and "text" in item:
            texts.append(str(item["text"]))
        else:
            text = getattr(item, "text", None)
            texts.append(text if isinstance(text, str) else json.dumps(item, default=str))
    return texts


def _extract_ticket(raw: Any, draft: ClickUpTicketDraft, list_id: str | None) -> ClickUpTicket | None:
    """Return a ClickUpTicket ONLY if the result contains a real created task (an `id`).

    The server can reply `isError=False` with a *text prompt* instead of a task (e.g. "Multiple
    Workspaces Detected", a premium-license notice, a sponsor message). Those carry no task id, so
    we return None — the caller treats that as a failure rather than a false success.
    """
    for text in _result_texts(raw):
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        task = data.get("task", data)
        if not isinstance(task, dict):
            continue
        tid = task.get("id")
        if not tid:
            continue
        list_field = task.get("list")
        resolved_list = list_field.get("id") if isinstance(list_field, dict) else list_id
        return ClickUpTicket(
            id=str(tid),
            name=task.get("name") or draft.name,
            url=task.get("url"),
            list_id=resolved_list,
        )
    return None


async def _create_tickets_via_mcp(
    drafts: Sequence[ClickUpTicketDraft], list_id: str
) -> list[ClickUpTicket]:
    created: list[ClickUpTicket] = []
    async with clickup_tools() as tools:
        create = _find_create_tool(tools)
        for draft in drafts:
            args: dict[str, Any] = {
                "name": draft.name,
                "description": draft.description,
                "priority": draft.priority,
                "listId": list_id,
            }
            if draft.due_date:
                args["dueDate"] = draft.due_date
            if draft.assignees:
                args["assignees"] = draft.assignees
            raw = await create.ainvoke(args)
            ticket = _extract_ticket(raw, draft, list_id)
            if ticket is None:
                # No task id came back → the server refused/prompted instead of creating.
                msg = " ".join(t.strip() for t in _result_texts(raw))[:400]
                raise RuntimeError(
                    f"ClickUp did not create '{draft.name}'. Server replied: {msg or '(empty)'}"
                )
            created.append(ticket)
    return created


def _run_in_proactor_loop(coro_factory) -> Any:
    """Run an async MCP interaction in a dedicated event loop on this (worker) thread.

    MCP's stdio transport spawns a subprocess, which on Windows requires a *Proactor* loop — but the
    API server forces the *Selector* loop for psycopg. So we run the whole exchange on a fresh loop
    in a worker thread (via `asyncio.to_thread`), isolated from whatever loop the server uses.
    """
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro_factory())
    finally:
        loop.close()


async def create_tickets(
    drafts: Sequence[ClickUpTicketDraft], list_id: str | None = None
) -> list[ClickUpTicket]:
    """Create each draft as a ClickUp task via the MCP server. Returns the created tickets.

    Raises a clear error if ClickUp isn't configured, no target List is set, or the server didn't
    actually create a task — the caller (ClickUpAgent) catches these and surfaces a friendly
    message instead of reporting a false success.
    """
    if not clickup_configured():
        raise RuntimeError(
            "ClickUp isn't configured. Set CLICKUP_API_KEY and CLICKUP_TEAM_ID in your .env."
        )
    target_list = list_id or settings.clickup_list_id
    if not target_list:
        raise RuntimeError("No target ClickUp List set. Add CLICKUP_LIST_ID to your .env.")

    drafts = list(drafts)
    return await asyncio.to_thread(
        _run_in_proactor_loop, lambda: _create_tickets_via_mcp(drafts, target_list)
    )


async def _update_ticket_via_mcp(task_id: str, name: str, fields: dict[str, Any]) -> ClickUpTicket:
    async with clickup_tools() as tools:
        update = _find_update_tool(tools)
        args: dict[str, Any] = {"taskId": task_id, **fields}
        raw = await update.ainvoke(args)
        ticket = _extract_ticket(raw, ClickUpTicketDraft(name=name), None)
        if ticket is not None:
            return ticket
        # update_task may reply without echoing the task JSON; if the tool didn't error, the change
        # applied — fall back to the known id/name. (isError replies raise before reaching here.)
        return ClickUpTicket(id=task_id, name=fields.get("name") or name)


async def update_ticket(
    task_id: str,
    name: str,
    *,
    new_name: str | None = None,
    priority: int | None = None,
    due_date: str | None = None,
    assignees: list[str] | None = None,
) -> ClickUpTicket:
    """Update an existing ClickUp task via MCP. Only the provided fields are changed."""
    if not clickup_configured():
        raise RuntimeError(
            "ClickUp isn't configured. Set CLICKUP_API_KEY and CLICKUP_TEAM_ID in your .env."
        )
    fields: dict[str, Any] = {}
    if new_name:
        fields["name"] = new_name
    if priority is not None:
        fields["priority"] = priority
    if due_date:
        fields["dueDate"] = due_date
    if assignees:
        fields["assignees"] = assignees
    if not fields:
        raise RuntimeError("Nothing to update — no changed fields were given.")
    return await asyncio.to_thread(
        _run_in_proactor_loop, lambda: _update_ticket_via_mcp(task_id, name, fields)
    )
