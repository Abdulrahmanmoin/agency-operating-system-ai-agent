"""Shared base for all agents: enforces the THINK → ACT → WRITE contract."""

from abc import ABC, abstractmethod
from typing import Any

from langgraph.errors import GraphBubbleUp

from agencyos.graph.state import AgencyState, AuditEntry, AuditPhase
from agencyos.observability.logging import get_logger


class BaseAgent(ABC):
    name: str
    role: str
    responsibility: str
    goal: str

    def __init__(self) -> None:
        self.log = get_logger(self.name)

    async def __call__(self, state: AgencyState) -> AgencyState:
        self.log.info("agent.start", agent=self.name)

        reasoning = await self.reason(state)
        state.audit_log.append(
            AuditEntry(agent=self.name, phase=AuditPhase.REASON, content=reasoning)
        )

        try:
            output = await self.act(state, reasoning)
        except GraphBubbleUp:
            # LangGraph control-flow signals (e.g. interrupt() for HITL) must propagate
            # untouched — they are not errors.
            raise
        except Exception as exc:  # noqa: BLE001 — top-level agent boundary
            self.log.error("agent.act.failed", agent=self.name, error=str(exc))
            state.audit_log.append(
                AuditEntry(agent=self.name, phase=AuditPhase.ERROR, content=str(exc))
            )
            state.attempt_count[self.name] = state.attempt_count.get(self.name, 0) + 1
            raise

        state.audit_log.append(
            AuditEntry(agent=self.name, phase=AuditPhase.ACT, content=str(output))
        )
        state = self.merge(state, output)
        self.log.info("agent.done", agent=self.name)
        return state

    def revision_note(self, state: AgencyState) -> str:
        """Feedback to fold into this agent's prompt when re-running after a QA rejection.

        Returns a non-empty instruction only when the latest validation rejected the package
        and named THIS agent as the one to revise — the validator→agent communication channel
        (via shared state). Empty string on a first/normal run.
        """
        vr = state.validation_report
        if vr is not None and not vr.approved and vr.target_agent == self.name:
            return (
                "\n\nIMPORTANT — a previous version of your output was rejected in QA review. "
                f"Revise specifically to address this feedback:\n{vr.feedback}"
            )
        return ""

    @abstractmethod
    async def reason(self, state: AgencyState) -> str:
        """Produce a reasoning trace BEFORE taking any action."""

    @abstractmethod
    async def act(self, state: AgencyState, reasoning: str) -> Any:
        """Call tools / produce structured output."""

    @abstractmethod
    def merge(self, state: AgencyState, output: Any) -> AgencyState:
        """Write the output into shared state."""
