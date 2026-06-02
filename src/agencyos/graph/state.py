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

    # Control
    next_action: str | None = None
    paused_for_input: bool = False
    attempt_count: dict[str, int] = Field(default_factory=dict)
    audit_log: list[AuditEntry] = Field(default_factory=list)
    run_summary: RunSummary | None = None

    # Free-form scratch for tools that don't fit a typed slot
    scratch: dict[str, Any] = Field(default_factory=dict)
