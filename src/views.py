"""Render AgencyState artifacts into the user-facing assistant message (markdown).

Used by the graph's finalize step so a turn shows the user *what was produced*, not just which
agents ran. UI-agnostic: the CLI prints this; a future web UI can render the same markdown.
"""

from graph.state import AgencyState


def _requirements_md(state: AgencyState) -> str:
    r = state.requirements
    lines = ["**Requirements**"]
    if r.client_goals:
        lines.append("- Goals: " + "; ".join(r.client_goals))
    if r.services:
        lines.append("- Services: " + ", ".join(r.services))
    lines.append(f"- Deadline: {r.deadline or 'not specified'}")
    lines.append(f"- Budget: {r.budget or 'not specified'}")
    lines.append(f"- Target audience: {r.target_audience or 'not specified'}")
    if r.constraints:
        lines.append("- Constraints: " + "; ".join(r.constraints))
    if r.priorities:
        lines.append("- Priorities: " + "; ".join(r.priorities))
    return "\n".join(lines)


def _plan_md(state: AgencyState) -> str:
    p = state.plan
    lines = ["**Project plan**", p.summary, ""]

    if p.objectives:
        lines.append("**Objectives**")
        lines += [f"- {o}" for o in p.objectives]
        lines.append("")

    if p.execution_strategy:
        lines += ["**Execution strategy**", p.execution_strategy, ""]

    lines.append("**Roadmap**")
    for m in p.phases or []:
        meta = " · ".join(
            x
            for x in [m.target_date, f"owner: {m.owner}" if m.owner else None, m.duration]
            if x
        )
        meta = f" ({meta})" if meta else ""
        lines.append(f"- **{m.name}**{meta}: {m.description}")
        if m.deliverables:
            lines.append("    - Deliverables: " + ", ".join(m.deliverables))
        if m.dependencies:
            lines.append("    - Depends on: " + ", ".join(m.dependencies))

    if p.success_metrics:
        lines += ["", "**Success metrics**"]
        lines += [f"- {s}" for s in p.success_metrics]

    return "\n".join(lines)


def _tasks_md(state: AgencyState) -> str:
    lines = [f"**Tasks** ({len(state.tasks)})"]
    for t in state.tasks:
        dep = f" — after {', '.join(t.depends_on)}" if t.depends_on else ""
        lines.append(f"- [{t.id}] P{t.priority} {t.title} ({t.milestone}){dep}")
    return "\n".join(lines)


def _risks_md(state: AgencyState) -> str:
    lines = [f"**Risks** ({len(state.risks)})"]
    for risk in state.risks:
        lines.append(f"- [{risk.severity.value.upper()}] {risk.title} — mitigation: {risk.mitigation}")
    return "\n".join(lines)


def _proposal_md(state: AgencyState) -> str:
    p = state.proposal
    sections: list[str] = ["**Proposal**", ""]

    def add(title: str, body: str) -> None:
        if body and body.strip():
            sections.extend([f"**{title}**", body.strip(), ""])

    add("Executive summary", p.executive_summary)
    add("Our approach", p.approach)
    add("Scope of work", p.scope)
    add("Deliverables", p.deliverables)
    add("Timeline", p.timeline)
    add("Investment", p.pricing)
    add("Key considerations & assumptions", p.assumptions)
    add("Next steps", p.next_steps)

    return "\n".join(sections).rstrip()


def _clarifications_md(state: AgencyState) -> str:
    if not state.clarifications:
        return "**Clarification** — no gaps found; the brief looks complete."
    lines = ["**Clarifications**"]
    for c in state.clarifications:
        ans = f" → {c.user_answer}" if c.user_answer else ""
        lines.append(f"- [{c.severity.value}] {c.field}: {c.issue}{ans}")
    return "\n".join(lines)


def _progress_md(state: AgencyState) -> str:
    # The agent already rendered the full PM report to markdown; show it verbatim.
    return state.progress_report or ""


def _validator_md(state: AgencyState) -> str:
    v = state.validation_report
    verdict = "approved ✅" if v.approved else "needs revision ❌"
    scores = ", ".join(f"{k} {val:.0f}/10" for k, val in v.scores.items())
    return f"**Quality review** — {verdict}" + (f" ({scores})" if scores else "")


_RENDERERS = {
    "requirement": (_requirements_md, lambda s: s.requirements is not None),
    "planning": (_plan_md, lambda s: s.plan is not None),
    "task_generation": (_tasks_md, lambda s: bool(s.tasks)),
    "risk": (_risks_md, lambda s: bool(s.risks)),
    "proposal": (_proposal_md, lambda s: s.proposal is not None),
    "clarification": (_clarifications_md, lambda s: True),
    "validator": (_validator_md, lambda s: s.validation_report is not None),
    "progress_report": (_progress_md, lambda s: s.progress_report is not None),
}
# NOTE: ClickUp tickets are intentionally NOT a Deliverables card — they live in ClickUp (and aren't
# meaningful as a DOCX/PDF download). The "✅ Created N tickets" chat message is the confirmation.


def summarize(state: AgencyState, agents: list[str]) -> str:
    """Render the outputs of the given agents that are present in state, as markdown."""
    sections: list[str] = []
    for name in agents:
        entry = _RENDERERS.get(name)
        if entry is None:
            continue
        render, present = entry
        if present(state):
            text = render(state)
            if text:
                sections.append(text)
    return "\n\n".join(sections)
