"""ClickUpAgent — turn generated tasks or a free-form request into ClickUp tickets via MCP.

Flow (one node, HITL-gated):
  1. LLM drafts the ticket(s) from the user's message + any generated tasks.
  2. The graph pauses (`interrupt`) to show the drafts and ask the user for the ticket details —
     due date, priority, and assignee (offering the real workspace members) — before anything is
     written. Replying applies the details; "cancel" aborts.
  3. The reply is parsed (LLM) into the drafts, then the tickets are created through the ClickUp
     MCP server (`tools/clickup_mcp.py`).

Creating tickets is an outward-facing, state-changing action, hence the mandatory HITL step.
"""

from langgraph.types import interrupt

from agencyos.agents.base import BaseAgent
from agencyos.graph.state import AgencyState, ClickUpTicket, ClickUpTicketDraft, TaskList, _Payload
from agencyos.llm import ainvoke_structured, get_chat_model
from agencyos.tools.clickup_mcp import (
    clickup_configured,
    create_tickets,
    list_workspace_members,
    update_ticket,
)

# References that mean "the ticket we were just talking about" rather than a specific name.
_GENERIC_REFS = {"this", "it", "that", "this one", "the ticket", "this ticket", "last", "the last one"}

# Phrases that mean "stop, don't create anything".
_CANCEL = {"n", "no", "nope", "cancel", "stop", "abort", "nevermind", "never mind", "don't", "dont"}


def _is_cancel(answer: object) -> bool:
    if isinstance(answer, bool):
        return not answer
    text = str(answer or "").strip().lower()
    return text in _CANCEL or text.startswith("cancel") or text.startswith("no ")


def _assignee_hint(members: list[dict]) -> str:
    if not members:
        return "I couldn't find any workspace members, so I'll leave the assignee empty."
    if len(members) == 1:
        return f"The only member is **{members[0]['username']}** (you) — say \"assign to me\" to assign it."
    names = ", ".join(m["username"] for m in members)
    return f"Available assignees: {names}."


def _resolve_target(existing: list[ClickUpTicket], ref: str | None) -> ClickUpTicket | None:
    """Pick which previously-created ticket an update refers to.

    Default = most recent. A specific name reference that matches exactly one wins. Returns None
    when it's genuinely ambiguous (a named ref matching none/several with multiple candidates), so
    the caller asks the user which one.
    """
    if not existing:
        return None
    if not ref or ref.strip().lower() in _GENERIC_REFS:
        return existing[-1]  # most recent
    r = ref.strip().lower()
    matches = [t for t in existing if r in t.name.lower() or t.name.lower() in r]
    if len(matches) == 1:
        return matches[0]
    if len(existing) == 1:
        return existing[0]
    return None  # ambiguous → ask


class ClickUpChange(_Payload):
    """The fields an update should change — each null unless the user asked to change it."""

    name: str | None = None
    priority: int | None = None
    due_date: str | None = None
    assignees: list[str] | None = None


class ClickUpPlan(_Payload):
    """LLM output: the action + the ticket(s) to create, plus flow signals."""

    action: str = "create"  # "create" | "update"
    target_ref: str | None = None  # update: which existing ticket the user pointed to
    tickets: list[ClickUpTicketDraft] | None = None
    needs_title: bool = False  # user wants a ticket but gave no subject to title it from
    skip_questions: bool = False  # user already gave/declined the details → don't ask again


class ClickUpAgent(BaseAgent):
    name = "clickup"
    role = "Delivery coordinator"
    responsibility = "Create or update ClickUp tickets from the project tasks or a free-form request."
    goal = "Get the agreed work into ClickUp, updating an existing ticket when the user refers to one."

    async def reason(self, state: AgencyState) -> str:
        n = len(state.tasks)
        return (
            f"Have {n} generated task(s) and the user's request; will draft the ClickUp ticket(s), "
            "confirm with the user, then create them via the ClickUp MCP server."
        )

    async def _draft(self, state: AgencyState, message: str | None = None) -> ClickUpPlan:
        from agencyos import prompts

        system = (
            f"You are the {self.role}. {self.responsibility} Goal: {self.goal} "
            "Only create what the user asked for; never fabricate tasks or titles."
        )
        import json

        existing = [{"name": t.name} for t in state.clickup_tickets]
        user = prompts.render(
            "tasks/draft_clickup_tickets.j2",
            user_message=message if message is not None else (state.last_user_message or ""),
            tasks_json=TaskList(tasks=state.tasks).model_dump_json(indent=2) if state.tasks else "[]",
            existing_json=json.dumps(existing),
        )
        model = get_chat_model("specialist", temperature=0.0).with_structured_output(ClickUpPlan)
        return await ainvoke_structured(
            model,
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
        )

    async def _parse_update(
        self, ticket_name: str, members: list[dict], message: str
    ) -> ClickUpChange:
        """Parse a change request into the fields to update (only what the user asked to change)."""
        import json

        from agencyos import prompts

        system = (
            f"You are the {self.role}. Extract ONLY the ticket fields the user asked to change. "
            "Never invent members, dates, priorities, or names."
        )
        user = prompts.render(
            "tasks/parse_clickup_update.j2",
            ticket_name=ticket_name,
            members_json=json.dumps(members, indent=2),
            user_message=message,
        )
        model = get_chat_model("specialist", temperature=0.0).with_structured_output(ClickUpChange)
        return await ainvoke_structured(
            model,
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
        )

    async def _update(self, state: AgencyState, plan: ClickUpPlan) -> dict:
        existing = state.clickup_tickets
        if not existing:
            return {
                "updated": [],
                "message": (
                    "I haven't created any ClickUp tickets in this conversation yet, so there's "
                    "nothing to update. Tell me the ticket to create."
                ),
            }
        if not clickup_configured():
            return {"updated": [], "message": "ClickUp isn't connected — add the keys to `.env` first."}

        target = _resolve_target(existing, plan.target_ref)
        if target is None:
            listing = "\n".join(f"- {t.name}" for t in existing)
            reply = interrupt(
                {
                    "kind": "confirmation",
                    "question": f"Which ticket should I update?\n{listing}\n\nName it, or say \"cancel\".",
                }
            )
            if _is_cancel(reply):
                return {"updated": [], "message": "Okay — I won't change any ClickUp ticket."}
            target = _resolve_target(existing, str(reply)) or existing[-1]

        members = await list_workspace_members()
        change = await self._parse_update(target.name, members, state.last_user_message or "")
        try:
            updated = await update_ticket(
                target.id or "",
                target.name,
                new_name=change.name,
                priority=change.priority,
                due_date=change.due_date,
                assignees=change.assignees,
            )
        except Exception as exc:  # noqa: BLE001 — surface ClickUp/MCP failures as a friendly message
            return {"updated": [], "message": f"I couldn't update the ClickUp ticket: {exc}"}
        return {"updated": [updated], "message": _update_message(target.name, change)}

    async def _apply_details(
        self, drafts: list[ClickUpTicketDraft], members: list[dict], answer: str
    ) -> list[ClickUpTicketDraft]:
        """Parse the user's free-text answer into the drafts (due date, priority, assignee ids)."""
        import json

        from agencyos import prompts

        system = (
            f"You are the {self.role}. Finalize ClickUp ticket details from the user's answer. "
            "Never invent members, dates, or tickets — leave a field unset rather than guessing."
        )
        user = prompts.render(
            "tasks/apply_clickup_details.j2",
            drafts_json=json.dumps([d.model_dump() for d in drafts], indent=2),
            members_json=json.dumps(members, indent=2),
            answer=answer,
        )
        model = get_chat_model("specialist", temperature=0.0).with_structured_output(ClickUpPlan)
        plan: ClickUpPlan = await ainvoke_structured(
            model,
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return plan.tickets or drafts  # fall back to the originals if the model returns nothing

    async def act(self, state: AgencyState, reasoning: str) -> dict:
        plan = await self._draft(state)

        # The user is changing a ticket we already created → update it, don't create a new one.
        if plan.action == "update":
            return await self._update(state, plan)

        details_text = state.last_user_message or ""
        skip_questions = plan.skip_questions

        # No subject to name the ticket from → ASK for it (never fabricate a title).
        if plan.needs_title and not plan.tickets:
            reply = interrupt(
                {
                    "kind": "confirmation",
                    "question": (
                        "What should the ClickUp ticket be about? Give a short title — and "
                        'optionally a due date, priority, or assignee — or say "cancel".'
                    ),
                }
            )
            if _is_cancel(reply):
                return {"created": [], "message": "Okay — I won't create a ClickUp ticket."}
            plan = await self._draft(state, message=str(reply))
            if not plan.tickets:  # fall back to the reply itself as the title
                plan.tickets = [ClickUpTicketDraft(name=str(reply).strip()[:120])]
            details_text = str(reply)
            skip_questions = True  # the reply IS the user's spec — don't ask again

        drafts = plan.tickets
        if not drafts:
            return {
                "created": [],
                "message": (
                    "I couldn't find anything to turn into a ClickUp ticket. Tell me what the "
                    "ticket should be, or generate the project tasks first and ask me to push them."
                ),
            }

        if not clickup_configured():
            listed = "\n".join(f"- {d.name}" for d in drafts)
            return {
                "created": [],
                "message": (
                    "ClickUp isn't connected yet, so I can't create these tickets:\n"
                    f"{listed}\n\nAdd **CLICKUP_API_KEY**, **CLICKUP_TEAM_ID**, and "
                    "**CLICKUP_LIST_ID** to the backend `.env`, then ask me again."
                ),
            }

        members = await list_workspace_members()

        if skip_questions:
            # The user already gave or declined the details — resolve from their message and create
            # straight away, no extra prompt.
            drafts = await self._apply_details(drafts, members, details_text)
        else:
            # Pause to gather the ticket details (and implicitly confirm) BEFORE writing anything.
            preview = "\n".join(f"- {d.name}" for d in drafts)
            question = (
                f"I'm ready to create {len(drafts)} ClickUp ticket(s):\n{preview}\n\n"
                "Before I do — any details? Tell me the **due date**, **priority** "
                "(urgent/high/normal/low), and **assignee**.\n"
                f"{_assignee_hint(members)}\n\n"
                'Reply with the details, "just create them" for the defaults, or "cancel".'
            )
            answer = interrupt(
                {
                    "kind": "confirmation",
                    "question": question,
                    "tickets": [d.model_dump() for d in drafts],
                    "members": members,
                }
            )
            if _is_cancel(answer):
                return {"created": [], "message": "Okay — I won't create those ClickUp tickets."}
            drafts = await self._apply_details(drafts, members, str(answer))

        try:
            created = await create_tickets(drafts)
        except Exception as exc:  # noqa: BLE001 — surface ClickUp/MCP failures as a friendly message
            return {
                "created": [],
                "message": f"I couldn't create the ClickUp tickets: {exc}",
            }

        return {"created": created, "message": _success_message(created)}

    def merge(self, state: AgencyState, output: dict) -> AgencyState:
        created: list[ClickUpTicket] = output.get("created", [])
        if created:
            state.clickup_tickets = [*state.clickup_tickets, *created]
        for u in output.get("updated", []):
            # replace the ticket in state by id, keeping conversation context accurate
            state.clickup_tickets = [u if t.id == u.id else t for t in state.clickup_tickets]
        if output.get("message"):
            state.last_assistant_message = output["message"]
        return state


def _success_message(tickets: list[ClickUpTicket]) -> str:
    lines = []
    for t in tickets:
        if t.url:
            lines.append(f"- [{t.name}]({t.url})")
        else:
            lines.append(f"- {t.name}")
    body = "\n".join(lines)
    return f"✅ Created {len(tickets)} ClickUp ticket(s):\n{body}"


def _update_message(name: str, change: "ClickUpChange") -> str:
    bits = []
    if change.name:
        bits.append(f"renamed to “{change.name}”")
    if change.priority is not None:
        bits.append(f"priority {change.priority}")
    if change.due_date:
        bits.append(f"due {change.due_date}")
    if change.assignees:
        bits.append("assignee set")
    detail = ", ".join(bits) if bits else "no changes detected"
    return f"✏️ Updated ClickUp ticket “{name}” ({detail})."


run = ClickUpAgent()
