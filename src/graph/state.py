"""Shared `AgencyState` passed between every agent node + inter-agent payload schemas."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class _Payload(BaseModel):
    """Base for LLM-produced payloads.

    Groq's function-calling validation rejects `null` for non-nullable array fields, and models
    sometimes emit `null` for "no items". So list fields here are typed `... | None` (schema
    accepts null) and coerced back to `[]` after validation, keeping downstream code list-safe.
    """

    @model_validator(mode="after")
    def _coerce_none_lists(self):
        for name, field in type(self).model_fields.items():
            if getattr(self, name) is None and "list[" in str(field.annotation):
                setattr(self, name, [])
        return self


# ─── Inter-agent payloads ─────────────────────────────────────────────


class TranscriptMeta(BaseModel):
    duration_sec: float
    speaker_count: int
    language: str


class Requirements(_Payload):
    client_goals: list[str] | None = None
    services: list[str] | None = None
    deadline: str | None = None
    budget: str | None = None
    constraints: list[str] | None = None
    priorities: list[str] | None = None
    target_audience: str | None = None


class ClarificationSeverity(str, Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class Clarification(BaseModel):
    field: str
    issue: str
    severity: ClarificationSeverity
    user_answer: str | None = None


class Milestone(_Payload):
    name: str
    description: str
    target_date: str | None = None
    deliverables: list[str] | None = None
    owner: str | None = None  # the role/team accountable for this phase
    duration: str | None = None  # rough length or effort (e.g. "2 weeks")
    dependencies: list[str] | None = None  # earlier milestones/inputs this phase needs first


class Plan(_Payload):
    summary: str
    objectives: list[str] | None = None  # strategic objectives the roadmap serves
    execution_strategy: str = ""  # how delivery will be approached, in prose
    phases: list[Milestone] | None = None
    success_metrics: list[str] | None = None  # measurable signals the project is on track/done


class Task(_Payload):
    id: str
    title: str
    description: str
    priority: int  # 1 = highest
    depends_on: list[str] | None = None
    milestone: str


class TaskList(_Payload):
    """Wrapper so the LLM can return a list of tasks via structured output."""

    tasks: list[Task] | None = None


class RiskSeverity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Risk(BaseModel):
    title: str
    description: str
    severity: RiskSeverity
    mitigation: str


class RiskList(_Payload):
    """Wrapper so the LLM can return a list of risks via structured output."""

    risks: list[Risk] | None = None


class ClickUpTicketDraft(_Payload):
    """A ticket the ClickUp agent proposes to create — shown to the user for confirmation
    BEFORE anything is written to the real workspace."""

    name: str
    description: str = ""
    priority: int = 3  # ClickUp scale: 1=Urgent, 2=High, 3=Normal, 4=Low
    source_task_id: str | None = None  # the generated Task this came from, if any
    due_date: str | None = None  # natural-language or unix-ms due date, gathered via HITL
    assignees: list[str] | None = None  # ClickUp user ids to assign, resolved from the HITL answer


class ClickUpTicket(BaseModel):
    """A ticket actually created in ClickUp (the MCP server's response)."""

    id: str | None = None
    name: str = ""
    url: str | None = None
    list_id: str | None = None


class Proposal(BaseModel):
    executive_summary: str
    scope: str
    timeline: str
    pricing: str
    next_steps: str
    approach: str = ""  # our methodology / how we'll deliver
    deliverables: str = ""  # concrete client-facing outputs they receive
    assumptions: str = ""  # key considerations & assumptions (risks framed constructively)


class ValidationReport(BaseModel):
    approved: bool
    scores: dict[str, float] = Field(default_factory=dict)
    feedback: str
    target_agent: str | None = None  # which agent to re-dispatch if not approved


class AuditPhase(str, Enum):
    REASON = "reason"
    ACT = "act"
    TOOL = "tool"
    ROUTE = "route"
    ERROR = "error"


class AuditEntry(BaseModel):
    agent: str
    phase: AuditPhase
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RunSummary(BaseModel):
    started_at: datetime
    ended_at: datetime | None = None
    total_agent_calls: int = 0
    total_tool_calls: int = 0
    total_tokens: int = 0
    retry_count: int = 0
    validator_scores: dict[str, float] = Field(default_factory=dict)
    output_path: str | None = None
    incidents: list[str] = Field(default_factory=list)


class Intent(_Payload):
    """Result of the Manager classifying a free-text user message into target agents."""

    agents: list[str] | None = Field(
        default=None,
        description="Agent names the user's request maps to (subset of the known agent roster).",
    )
    full_pipeline: bool = Field(
        default=False,
        description="True when the user asked for an end-to-end run (all agents).",
    )
    regenerate: bool = Field(
        default=False,
        description="True when the user asked to redo/regenerate an existing result from scratch.",
    )
    rationale: str = Field(
        default="",
        description="Why this mapping was chosen; persisted to the audit log.",
    )


class PendingConfirmation(BaseModel):
    """A yes/no question the Manager raises before auto-running missing prerequisites."""

    question: str
    target_agents: list[str]  # what the user originally asked for
    prerequisites: list[str]  # missing upstream agents we'd run first if confirmed


# ─── The big one ──────────────────────────────────────────────────────


class AgencyState(BaseModel):
    # Identity
    conversation_id: UUID = Field(default_factory=uuid4)
    user_id: str
    client_id: str | None = None

    # Inputs
    audio_path: Path | None = None
    notes_path: Path | None = None
    notes_text: str | None = None  # text loaded from notes_path (txt/docx/pdf)
    raw_user_message: str | None = None

    # Agent outputs
    transcript: str | None = None
    transcript_meta: TranscriptMeta | None = None
    requirements: Requirements | None = None
    clarifications: list[Clarification] = Field(default_factory=list)
    plan: Plan | None = None
    tasks: list[Task] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    proposal: Proposal | None = None
    validation_report: ValidationReport | None = None
    clickup_tickets: list[ClickUpTicket] = Field(default_factory=list)
    progress_report: str | None = None  # rendered PM progress report (ClickUp ↔ GitHub), markdown

    # Conversation control (intent-driven, turn-based)
    last_user_message: str | None = None
    last_assistant_message: str | None = None
    intent: Intent | None = None
    pending_confirmation: PendingConfirmation | None = None
    capabilities_offered: bool = False  # auto-offer the menu only on the first task-less turn
    dispatch_queue: list[str] = Field(default_factory=list)  # agents still to run this turn

    # Execution control
    next_action: str | None = None
    paused_for_input: bool = False
    attempt_count: dict[str, int] = Field(default_factory=dict)
    audit_log: list[AuditEntry] = Field(default_factory=list)
    run_summary: RunSummary | None = None

    # Free-form scratch for tools that don't fit a typed slot
    scratch: dict[str, Any] = Field(default_factory=dict)

    def source_material(self) -> str | None:
        """The working text agents extract from: an audio transcript or loaded notes."""
        return self.transcript or self.notes_text
