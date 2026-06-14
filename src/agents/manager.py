"""ManagerAgent — orchestrator + intent classifier. See ARCHITECTURE.md §2.

The Manager does NOT do specialist work. Its job is to (1) interpret the user's free-text
request into a set of target agents (`classify_intent`), and (2) decide, given the current
state, whether prerequisites are missing and a confirmation is needed (`resolve_prerequisites`).
"""

from agents.base import BaseAgent
from graph.routing import (
    KNOWN_AGENTS,
    missing_prerequisites,
    topological_order,
)
from graph.state import AgencyState, Intent, PendingConfirmation
from llm import ainvoke_structured, get_chat_model


class ManagerAgent(BaseAgent):
    name = "manager"
    role = "Chief of Staff"
    responsibility = "Interpret requests, route to specialists, handle validator feedback, decide completion."
    goal = "Deliver what the user asked for with the minimum necessary agents and retries."

    async def classify_intent(self, state: AgencyState) -> Intent:
        """Map the user's latest free-text message to target agents via the LLM."""
        import prompts
        from agents.registry import capabilities

        system = prompts.render("system/manager_intent.j2", capabilities=capabilities())
        model = get_chat_model("manager", temperature=0.0).with_structured_output(Intent)
        intent: Intent = await ainvoke_structured(
            model,
            [
                {"role": "system", "content": system},
                {"role": "user", "content": state.last_user_message or ""},
            ],
        )
        # Defensive: drop hallucinated agent names; keep order the model gave.
        intent.agents = [a for a in intent.agents if a in KNOWN_AGENTS]
        return intent

    def resolve_prerequisites(
        self, state: AgencyState, intent: Intent
    ) -> PendingConfirmation | None:
        """If the requested agents need upstream outputs that don't exist yet, build a
        confirmation question. Returns None when everything needed is already present."""
        if intent.full_pipeline:
            return None  # full pipeline runs everything in order; nothing to confirm

        prereqs: list[str] = []
        for agent in intent.agents:
            for p in missing_prerequisites(state, agent):
                if p not in prereqs and p not in intent.agents:
                    prereqs.append(p)
        if not prereqs:
            return None

        ordered = topological_order(prereqs)
        pretty = ", ".join(p.replace("_", " ") for p in ordered)
        want = ", ".join(a.replace("_", " ") for a in intent.agents)
        return PendingConfirmation(
            question=(
                f"To do {want}, I first need to run: {pretty}. "
                f"Shall I run those first? (yes/no)"
            ),
            target_agents=list(intent.agents),
            prerequisites=ordered,
        )

    # ── BaseAgent contract (Manager produces no specialist payload) ──
    async def reason(self, state: AgencyState) -> str:
        return "Manager orchestration step; routing handled by the graph."

    async def act(self, state: AgencyState, reasoning: str) -> dict:
        return {"acknowledged": True}

    def merge(self, state: AgencyState, output: dict) -> AgencyState:
        return state


run = ManagerAgent()
