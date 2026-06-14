"""RiskAnalysisAgent — flag project risks, validated against web benchmarks (Tavily) via Groq."""

from agents.base import BaseAgent
from graph.state import AgencyState, AuditEntry, AuditPhase, RiskList, TaskList
from llm import ainvoke_structured, get_chat_model


class RiskAnalysisAgent(BaseAgent):
    name = "risk"
    role = "Risk auditor"
    responsibility = "Detect unrealistic deadlines, unclear scope, budget mismatches, bottlenecks."
    goal = "Surface every material risk with severity and mitigation before client sign-off."

    async def reason(self, state: AgencyState) -> str:
        from config import settings

        will_search = bool(settings.tavily_api_key)
        return (
            f"Have plan={'yes' if state.plan else 'no'}, {len(state.tasks)} task(s). Will "
            f"{'validate the timeline/budget against live web benchmarks (Tavily) and ' if will_search else ''}"
            "flag deadline, budget, scope, and bottleneck risks with severity and mitigations."
        )

    async def _gather_web_context(self, state: AgencyState) -> str:
        """Use Tavily to pull market benchmarks. Degrades gracefully (returns "") if Tavily is
        unconfigured or fails — risk analysis still proceeds from the plan/tasks alone."""
        from config import settings

        if not settings.tavily_api_key:
            return ""

        from tools.web_search import tavily_search

        reqs = state.requirements
        services = ", ".join(reqs.services) if reqs and reqs.services else "the requested services"
        query = (
            f"realistic timeline and budget to deliver {services} for a small business in 2026"
        )
        try:
            res = await tavily_search(query, max_results=3)
        except Exception as exc:  # noqa: BLE001 — Tavily is best-effort, never fatal
            self.log.warning("risk.web_search.failed", error=str(exc))
            return ""

        state.audit_log.append(
            AuditEntry(agent=self.name, phase=AuditPhase.TOOL, content=f"tavily_search: {query!r}")
        )
        lines: list[str] = []
        if res.get("answer"):
            lines.append("Benchmark summary: " + res["answer"])
        for r in res.get("results", [])[:3]:
            lines.append(f"- {r.get('title')}: {(r.get('content') or '')[:200]}")
        return "\n".join(lines)

    async def act(self, state: AgencyState, reasoning: str) -> RiskList:
        import prompts

        if state.plan is None and not state.tasks:
            return RiskList()

        web_context = await self._gather_web_context(state)
        system = (
            f"You are the {self.role}. {self.responsibility} Goal: {self.goal} "
            "Report only genuine, material risks grounded in the inputs; do not pad the list."
        )
        user = prompts.render(
            "tasks/analyze_risks.j2",
            requirements_json=(
                state.requirements.model_dump_json(indent=2) if state.requirements else "null"
            ),
            plan_json=(state.plan.model_dump_json(indent=2) if state.plan else "null"),
            tasks_json=TaskList(tasks=state.tasks).model_dump_json(indent=2),
            web_context=web_context or "(no external benchmark data available)",
        ) + self.revision_note(state)

        model = get_chat_model("specialist", temperature=0.2).with_structured_output(RiskList)
        return await ainvoke_structured(
            model,
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )

    def merge(self, state: AgencyState, output: RiskList) -> AgencyState:
        state.risks = output.risks
        return state


run = RiskAnalysisAgent()
