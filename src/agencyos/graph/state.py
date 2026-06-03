"""Shared `AgencyState` passed between every agent node + inter-agent payload schemas."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ─── Inter-agent payloads ─────────────────────────────────────────────


class TranscriptMeta(BaseModel):
    duration_sec: float
    speaker_count: int
    language: str


class Requirements(BaseModel):
    client_goals: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    deadline: str | None = None
    budget: str | None = None
    constraints: list[str] = Field(default_factory=list)
    priorities: list[str] = Field(default_factory=list)
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


class Milestone(BaseModel):
    name: str
    description: str
    target_date: str | None = None
    deliverables: list[str] = Field(default_factory=list)


class Plan(BaseModel):
    summary: str
    phases: list[Milestone] = Field(default_factory=list)


class Task(BaseModel):
    id: str
    title: str
    description: str
    priority: int  # 1 = highest
    depends_on: list[str] = Field(default_factory=list)
    milestone: str


class RiskSeverity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Risk(BaseModel):
    title: str
    description: str
    severity: RiskSeverity
    mitigation: str


class Proposal(BaseModel):
    executive_summary: str
    scope: str
    timeline: str
    pricing: str
    next_steps: str


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


class Intent(BaseModel):
    """Result of the Manager classifying a free-text user message into target agents."""

    agents: list[str] = Field(
        default_factory=list,
        description="Agent names the user's request maps to (subset of the known agent roster).",
    )
    full_pipeline: bool = Field(
        default=False,
        description="True when the user asked for an end-to-end run (all agents).",
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
