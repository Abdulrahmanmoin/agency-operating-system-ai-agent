"""ProgressReportAgent — report project progress to the PM by joining ClickUp ↔ GitHub.

Flow (one node, read-only — no HITL, no writes):
  1. Read the ClickUp tickets (who each is assigned to) from the configured List.
  2. Read the GitHub repo's branches + pull requests.
  3. Match each ticket to its branch/PR by the ticket id in the branch name (e.g. ``CU-<id>``) and
     derive a status (done / in progress / not started).
  4. Render a PM-facing report: overall % complete, what remains, and where each developer stands.

The report is shown in chat AND stored as a downloadable Deliverable (DOCX/PDF). Nothing is written
to GitHub or ClickUp, so there's no confirmation step.
"""

from agents.base import BaseAgent
from graph.state import AgencyState
from tools.clickup_mcp import list_tasks
from tools.github import (
    github_configured,
    list_branches,
    list_pulls,
    match_tickets,
    render_report,
)


class ProgressReportAgent(BaseAgent):
    name = "progress_report"
    role = "Delivery analyst"
    responsibility = (
        "Report project progress to the PM by matching ClickUp tickets to the GitHub "
        "branches and pull requests that complete them."
    )
    goal = (
        "Tell the PM how much of the project is done and how much remains, and where each "
        "developer stands on their assigned tickets."
    )

    async def reason(self, state: AgencyState) -> str:
        return (
            "Will read the ClickUp tickets and the GitHub branches/PRs, match them by the ticket "
            "id in the branch name, then compute per-developer and overall completion for the PM."
        )

    async def act(self, state: AgencyState, reasoning: str) -> dict:
        if not github_configured():
            return {
                "message": (
                    "GitHub isn't connected, so I can't build a progress report. Add "
                    "**GITHUB_TOKEN** (read-only) and **GITHUB_REPO** (`owner/name`) to the backend "
                    "`.env`, then ask me again."
                )
            }

        tickets = await list_tasks()
        if not tickets:
            # Fall back to tickets created earlier in this conversation (no assignee data on these).
            tickets = [
                {"id": t.id, "name": t.name, "assignees": [], "status": None}
                for t in state.clickup_tickets
                if t.id
            ]
        if not tickets:
            return {
                "message": (
                    "I don't see any ClickUp tickets to report on yet. Create the project tickets "
                    "in ClickUp (and set **CLICKUP_LIST_ID** in `.env`) first, then ask me for the "
                    "progress report."
                )
            }

        branches = await list_branches()
        pulls = await list_pulls()
        progress = match_tickets(tickets, branches, pulls)
        report = render_report(progress)
        return {"report": report, "message": report}

    def merge(self, state: AgencyState, output: dict) -> AgencyState:
        if output.get("report"):
            state.progress_report = output["report"]
        if output.get("message"):
            state.last_assistant_message = output["message"]
        return state


run = ProgressReportAgent()
