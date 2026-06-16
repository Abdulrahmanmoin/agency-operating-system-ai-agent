"""Read-only GitHub access for the Progress Report agent.

The agency's flow is: a ClickUp ticket is created and assigned to a developer, the developer cuts a
branch named after that ticket (e.g. ``CU-86abc123-login`` or ``feature/CU-86abc123``), works on it,
then opens a PR. So the **branch name carries the ClickUp ticket id**, which is the join key between
the two systems. This module reads the repo's branches and pull requests (REST, read-only) and
matches them back to tickets, deriving a per-ticket status:

    PR merged          -> done
    PR open / branch   -> in progress
    no branch or PR    -> not started

Everything here is read-only (`GET` only) — we never write to GitHub. Calls degrade to ``[]`` when
unconfigured or on any error, so the agent simply reports "no GitHub data" rather than crashing.
"""

from dataclasses import dataclass
from typing import Any

from config import settings

_API = "https://api.github.com"


def github_configured() -> bool:
    """True when we have enough to read the repo (a token + an ``owner/name`` repo)."""
    return bool(settings.github_token and settings.github_repo)


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def _get(path: str, params: dict[str, Any]) -> Any:
    import httpx

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{_API}{path}", headers=_headers(), params=params)
        resp.raise_for_status()
        return resp.json()


async def list_branches() -> list[dict[str, str]]:
    """Return the repo's branches as ``[{"name": ...}]`` (read-only). ``[]`` if unconfigured/error."""
    if not github_configured():
        return []
    try:
        data = await _get(f"/repos/{settings.github_repo}/branches", {"per_page": 100})
    except Exception:  # noqa: BLE001 — progress reporting is best-effort, never fatal
        return []
    return [{"name": str(b.get("name", ""))} for b in data if isinstance(b, dict)]


async def list_pulls() -> list[dict[str, Any]]:
    """Return the repo's PRs (all states) as a flat list (read-only). ``[]`` if unconfigured/error.

    Each item: ``{head_ref, author, state, merged, url, title}`` — ``merged`` is True when the PR
    was actually merged (``merged_at`` set), not merely closed.
    """
    if not github_configured():
        return []
    try:
        data = await _get(
            f"/repos/{settings.github_repo}/pulls", {"state": "all", "per_page": 100}
        )
    except Exception:  # noqa: BLE001
        return []
    pulls: list[dict[str, Any]] = []
    for p in data:
        if not isinstance(p, dict):
            continue
        pulls.append(
            {
                "head_ref": str((p.get("head") or {}).get("ref", "")),
                "author": str((p.get("user") or {}).get("login", "")) or None,
                "state": p.get("state"),  # "open" | "closed"
                "merged": p.get("merged_at") is not None,
                "url": p.get("html_url"),
                "title": p.get("title"),
            }
        )
    return pulls


# ─── ticket ↔ GitHub matching (pure, fully unit-testable) ─────────────


@dataclass
class TicketProgress:
    """One ClickUp ticket's status, derived from the GitHub branch/PR that references it."""

    ticket_id: str
    name: str
    assignee: str
    status: str  # "done" | "in_progress" | "not_started"
    branch: str | None = None
    pr_url: str | None = None


def _branch_refs_ticket(branch_name: str, ticket_id: str) -> bool:
    """Whether a branch name references a ClickUp ticket id.

    Matches the team's convention — ``CU-<id>-slug`` / ``feature/CU-<id>`` — and, as a fallback,
    the bare id appearing anywhere in the name. ClickUp ids are long alphanumerics, so a bare-id
    match is safe from collisions.
    """
    if not ticket_id:
        return False
    b = branch_name.lower()
    t = ticket_id.lower()
    return f"cu-{t}" in b or t in b


def match_tickets(
    tickets: list[dict[str, Any]],
    branches: list[dict[str, str]],
    pulls: list[dict[str, Any]],
) -> list[TicketProgress]:
    """Match each ClickUp ticket to its GitHub branch/PR and derive a status.

    ``tickets`` items: ``{id, name, assignees: [username, ...], status?}``.
    A merged PR wins (done); else an open PR or any matching branch means in-progress; else
    not-started. The reporting developer is the ticket's first ClickUp assignee.
    """
    branch_names = [b.get("name", "") for b in branches]
    result: list[TicketProgress] = []
    for tk in tickets:
        tid = str(tk.get("id", ""))
        ticket_pulls = [p for p in pulls if _branch_refs_ticket(p.get("head_ref", ""), tid)]
        merged = [p for p in ticket_pulls if p.get("merged")]
        open_prs = [p for p in ticket_pulls if p.get("state") == "open"]
        ticket_branches = [b for b in branch_names if _branch_refs_ticket(b, tid)]

        if merged:
            status, branch, pr_url = "done", merged[0].get("head_ref"), merged[0].get("url")
        elif open_prs:
            status, branch, pr_url = "in_progress", open_prs[0].get("head_ref"), open_prs[0].get("url")
        elif ticket_branches:
            status, branch, pr_url = "in_progress", ticket_branches[0], None
        else:
            status, branch, pr_url = "not_started", None, None

        assignees = tk.get("assignees") or []
        assignee = assignees[0] if assignees else "Unassigned"
        result.append(
            TicketProgress(
                ticket_id=tid,
                name=str(tk.get("name", "")),
                assignee=assignee,
                status=status,
                branch=branch,
                pr_url=pr_url,
            )
        )
    return result


_STATUS_EMOJI = {"done": "✅", "in_progress": "🔄", "not_started": "⬜"}


def _ticket_note(it: TicketProgress) -> str:
    if it.pr_url:
        return f" — [PR]({it.pr_url})"
    if it.branch:
        return f" — branch `{it.branch}`"
    return ""


def render_report(items: list[TicketProgress]) -> str:
    """Render the matched tickets into a PM-facing markdown progress report (deterministic)."""
    total = len(items)
    if total == 0:
        return "**Project progress** — no ClickUp tickets found to report on yet."

    done = sum(1 for i in items if i.status == "done")
    pct = round(100 * done / total)
    remaining = total - done

    lines = [
        f"**Project progress — {pct}% complete** "
        f"({done}/{total} tickets done · {remaining} remaining)",
        "",
        "**By developer**",
    ]

    by_dev: dict[str, list[TicketProgress]] = {}
    for it in items:
        by_dev.setdefault(it.assignee, []).append(it)

    finished_devs: list[str] = []
    for dev in sorted(by_dev):
        dev_items = by_dev[dev]
        d = sum(1 for i in dev_items if i.status == "done")
        ip = sum(1 for i in dev_items if i.status == "in_progress")
        ns = sum(1 for i in dev_items if i.status == "not_started")
        t = len(dev_items)
        if d == t:
            lines.append(f"- **{dev}** — ✅ all {t} ticket(s) done")
            finished_devs.append(dev)
        else:
            lines.append(f"- **{dev}** — {d}/{t} done ({ip} in progress, {ns} not started)")
        for it in dev_items:
            lines.append(f"    - {_STATUS_EMOJI[it.status]} {it.name}{_ticket_note(it)}")

    # The "dev1 finished before dev2" callout the PM cares about.
    if finished_devs and len(finished_devs) < len(by_dev):
        behind = [d for d in sorted(by_dev) if d not in finished_devs]
        lines += [
            "",
            f"**Heads up:** {', '.join(finished_devs)} finished all assigned tickets; "
            f"{', '.join(behind)} still {'has' if len(behind) == 1 else 'have'} open work.",
        ]

    return "\n".join(lines)
