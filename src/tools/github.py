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
    clickup_status: str | None = None  # the ticket's own status text in ClickUp (e.g. "in progress")
    pr_state: str | None = None  # "merged" | "open" | "closed" | None (no PR)
    has_branch: bool = False  # a branch referencing this ticket has been pushed


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
            status, branch, pr_url, pr_state = (
                "done", merged[0].get("head_ref"), merged[0].get("url"), "merged"
            )
        elif open_prs:
            status, branch, pr_url, pr_state = (
                "in_progress", open_prs[0].get("head_ref"), open_prs[0].get("url"), "open"
            )
        elif ticket_branches:
            status, branch, pr_url, pr_state = "in_progress", ticket_branches[0], None, None
        elif ticket_pulls:  # a PR exists but was closed without merging
            status, branch, pr_url, pr_state = (
                "not_started", ticket_pulls[0].get("head_ref"), ticket_pulls[0].get("url"), "closed"
            )
        else:
            status, branch, pr_url, pr_state = "not_started", None, None, None

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
                clickup_status=tk.get("status"),
                pr_state=pr_state,
                has_branch=bool(ticket_branches),
            )
        )
    return result


# Plain-text tags (not emoji) so the report renders identically in chat, DOCX and PDF — emoji
# collapse to a "tofu" box in the document fonts and can't be told apart.
_STATUS_LABEL = {"done": "[DONE]", "in_progress": "[IN PROGRESS]", "not_started": "[NOT STARTED]"}
_STATUS_ORDER = {"done": 0, "in_progress": 1, "not_started": 2}


def _clickup_phrase(it: TicketProgress) -> str:
    """The ticket's own status as it stands in ClickUp."""
    return f"*{it.clickup_status}*" if it.clickup_status else "*no status set*"


def _github_phrase(it: TicketProgress) -> str:
    """Plain-English GitHub state for one ticket: code pushed? PR opened? merged?"""
    if it.pr_state == "merged" or (it.status == "done" and it.pr_url):
        link = f" ([PR]({it.pr_url}))" if it.pr_url else ""
        return f"PR merged into `main`{link}"
    if it.pr_state == "open":
        link = f" ([PR]({it.pr_url}))" if it.pr_url else ""
        return f"PR open — **waiting on merge**{link}"
    if it.pr_state == "closed":
        link = f" ([PR]({it.pr_url}))" if it.pr_url else ""
        return f"PR closed without merging{link}"
    if it.has_branch or it.branch:
        return f"code pushed to branch `{it.branch}`, no PR opened yet"
    return "no branch or PR yet"


def render_report(items: list[TicketProgress]) -> str:
    """Render the matched tickets into a PM-facing markdown progress report (deterministic).

    The report is intentionally detailed for delivery reviews: an overall roll-up, a status
    summary, a "waiting on merge" spotlight, a per-developer breakdown that states each ticket's
    ClickUp status *and* its GitHub state (code pushed / PR open / merged), the finished-vs-behind
    callout, recommended next actions, and a legend. Output is plain markdown (bold headings,
    bullets, indented sub-bullets) so the DOCX/PDF exporters render it directly.
    """
    total = len(items)
    if total == 0:
        return "**Project progress** — no ClickUp tickets found to report on yet."

    done = sum(1 for i in items if i.status == "done")
    in_prog = sum(1 for i in items if i.status == "in_progress")
    not_started = sum(1 for i in items if i.status == "not_started")
    pct = round(100 * done / total)
    remaining = total - done

    merged_prs = [i for i in items if i.pr_state == "merged"]
    open_prs = [i for i in items if i.pr_state == "open"]
    branch_only = [i for i in items if i.has_branch and not i.pr_state]

    lines = [
        f"**Project progress — {pct}% complete** "
        f"({done}/{total} tickets done · {remaining} remaining)",
        "",
        "This report joins every ClickUp ticket to the GitHub branch and pull request that delivers "
        "it. A ticket is counted **done** only once its PR is merged into `main`; until then it is "
        "in progress (code pushed, or a PR open and awaiting review) or not started.",
        "",
        "**Status summary**",
        f"- Done — PR merged into `main`: **{done}**",
        f"- In progress: **{in_prog}** "
        f"({len(branch_only)} with code pushed but no PR yet, {len(open_prs)} with a PR open)",
        f"- Not started — no branch or PR yet: **{not_started}**",
        f"- Pull requests: **{len(merged_prs)} merged**, **{len(open_prs)} open**, "
        f"{len(branch_only)} branch(es) pushed without a PR",
    ]

    # Spotlight what the PM can unblock right now.
    if open_prs:
        lines += ["", "**Waiting on merge** (open PRs ready for review)"]
        for it in open_prs:
            link = f" — [PR]({it.pr_url})" if it.pr_url else ""
            lines.append(f"- {it.name} — {it.assignee}{link}")

    lines += ["", "**By developer**"]

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
            lines.append(f"- **{dev}** — [DONE] all {t} ticket(s) done")
            finished_devs.append(dev)
        else:
            lines.append(f"- **{dev}** — {d}/{t} done ({ip} in progress, {ns} not started)")
        for it in sorted(dev_items, key=lambda x: (_STATUS_ORDER[x.status], x.name)):
            lines.append(
                f"    - {_STATUS_LABEL[it.status]} {it.name} — "
                f"ClickUp: {_clickup_phrase(it)} · GitHub: {_github_phrase(it)}"
            )

    # The "dev1 finished before dev2" callout the PM cares about.
    if finished_devs and len(finished_devs) < len(by_dev):
        behind = [d for d in sorted(by_dev) if d not in finished_devs]
        lines += [
            "",
            f"**Heads up:** {', '.join(finished_devs)} finished all assigned tickets; "
            f"{', '.join(behind)} still {'has' if len(behind) == 1 else 'have'} open work.",
        ]

    # Concrete next actions, derived straight from the data.
    actions: list[str] = []
    for it in open_prs:
        actions.append(
            f"Review and merge the PR for **{it.name}** ({it.assignee}) to close it out."
        )
    for it in branch_only:
        actions.append(
            f"Ask {it.assignee} to open a PR for **{it.name}** — code is pushed but unreviewed."
        )
    if not actions:
        actions.append(
            "No PRs are awaiting action right now; the next work is in the not-started tickets above."
        )
    lines += ["", "**Recommended next actions**"]
    lines += [f"- {a}" for a in actions]

    lines += [
        "",
        "**How to read this**",
        "- **[DONE]** — the ticket's pull request is merged into `main`.",
        "- **[IN PROGRESS]** — a branch is pushed, or a PR is open but not yet merged.",
        "- **[NOT STARTED]** — no branch or PR references this ticket yet.",
    ]

    return "\n".join(lines)
