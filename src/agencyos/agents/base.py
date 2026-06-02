"""Shared base for all agents: enforces the THINK → ACT → WRITE contract."""

from abc import ABC, abstractmethod
from typing import Any

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

    @abstractmethod
    async def reason(self, state: AgencyState) -> str:
        """Produce a reasoning trace BEFORE taking any action."""

    @abstractmethod
    async def act(self, state: AgencyState, reasoning: str) -> Any:
        """Call tools / produce structured output."""

    @abstractmethod
    def merge(self, state: AgencyState, output: Any) -> AgencyState:
        """Write the output into shared state."""
