# AgencyOS — Architecture

> **Mission.** Convert a raw client interaction (meeting recording or notes) into a validated, packaged project proposal — autonomously, with full reasoning traceability.

---

## 1. Why multiple agents (not a single LLM)

| Concern | Single LLM with prompts | AgencyOS (multi-agent) |
|---|---|---|
| Context size | One window → degrades with long briefs + history | Each agent sees only what it needs |
| Tool scoping | Every tool exposed to one model | Each agent only accesses its permitted tools |
| Reasoning audit | One opaque output | Every agent emits a `Reasoning` block → audit log |
| Quality control | None | Validator + Risk agents catch errors before client |
| Failure isolation | Whole run fails | Failed specialist → Manager retries with feedback |
| Extensibility | New requirement = bigger prompt | New requirement = new agent node |

---

## 2. Agent roster (11 agents)

Every agent declares **Role / Responsibility / Goal / Tools / Inputs / Outputs**.

### 👑 ManagerAgent (Orchestrator)
- **Role:** Chief of Staff
- **Responsibility:** Read state, decide the next agent to invoke, route, handle validator feedback, decide when run is complete
- **Goal:** Deliver a validator-approved project package with minimum retries
- **Tools:** `create_plan`, `route_to(agent)`, `mark_complete`, `escalate_to_user`
- **Inputs:** Full `AgencyState`
- **Outputs:** `next_action`, `rationale`, updated `plan`

### 🎙️ TranscriptionAgent
- **Role:** Audio-to-text specialist
- **Responsibility:** Convert uploaded audio (`mp3` / `wav` / `mp4`) → cleaned transcript with speaker segmentation
- **Goal:** Produce a faithful, timestamp-clean transcript ready for downstream extraction
- **Tools:** `groq_whisper_transcribe`, `speaker_segmenter`, `timestamp_normalizer`
- **Inputs:** `state.audio_path`
- **Outputs:** `state.transcript`, `state.transcript_meta`
- **Skip condition:** Runs only if input is audio; bypassed for text uploads

### 📋 RequirementAnalysisAgent
- **Role:** Brief decoder
- **Responsibility:** Extract structured requirements from transcript/notes: client goals, services needed, deadlines, budget, constraints, priorities
- **Goal:** Convert messy conversation → typed `Requirements` object with high recall
- **Tools:** `entity_extractor`, `structured_output_parser`
- **Inputs:** `state.transcript` or `state.notes`
- **Outputs:** `state.requirements: Requirements`

### ❓ ClarificationAgent
- **Role:** Gap finder
- **Responsibility:** Detect vague, missing, or contradictory requirements
- **Goal:** Reach a complete, unambiguous requirement spec before planning
- **Tools:** `rubric_checker`, `contradiction_detector`, `hitl_prompt` (pauses graph)
- **Inputs:** `state.requirements`
- **Outputs:** `state.clarifications: list[Clarification]`, may set `state.paused_for_input = True`
- **HITL flow:** If critical gaps exist → emit graph interrupt → CLI prompts user → answers merged into `state.requirements` → graph resumes

### 🧠 PlanningAgent
- **Role:** Strategist
- **Responsibility:** Build roadmap, milestones, phases, execution strategy from requirements
- **Goal:** Produce a phased plan that maps every requirement to a milestone
- **Tools:** `template_loader` (past-project plan templates), `web_search` (Tavily — industry benchmarks)
- **Inputs:** `state.requirements`
- **Outputs:** `state.plan: Plan`

### ⚙️ TaskGenerationAgent
- **Role:** Project decomposer
- **Responsibility:** Generate tasks, subtasks, priorities, dependencies (Jira-style)
- **Goal:** Each milestone in `state.plan` is decomposed into actionable, dependency-ordered tasks
- **Tools:** `structured_output_parser`, `dag_validator`
- **Inputs:** `state.plan`
- **Outputs:** `state.tasks: list[Task]`

### ⚠️ RiskAnalysisAgent
- **Role:** Risk auditor
- **Responsibility:** Detect unrealistic deadlines, unclear scope, budget mismatches, bottlenecks
- **Goal:** Surface every material risk with severity + mitigation suggestion before client sign-off
- **Tools:** `web_search` (Tavily — verify market benchmarks), `calculator` (deadline math)
- **Inputs:** `state.plan`, `state.tasks`, `state.requirements`
- **Outputs:** `state.risks: list[Risk]`

### 🧪 ValidatorAgent
- **Role:** QA reviewer
- **Responsibility:** Check consistency, duplicate tasks, logical correctness, missing deliverables across all artifacts
- **Goal:** Approve the package only when it meets every rubric dimension
- **Tools:** `rubric_loader`, `structured_scoring`
- **Inputs:** `state.requirements`, `state.plan`, `state.tasks`, `state.risks`
- **Outputs:** `ValidationReport { approved: bool, scores: dict, feedback: str, target_agent: str | None }`
- **Routing impact:** If `approved=False` → Manager re-dispatches `target_agent` with `feedback` injected (max 3 cycles)

### 📊 ProposalAgent
- **Role:** Client communicator
- **Responsibility:** Draft proposal text, project summary, client-ready report, meeting recap
- **Goal:** Produce client-facing documents that read as if written by a senior account manager
- **Tools:** `template_loader`, `structured_output_parser`
- **Inputs:** Everything except risks (gets risks only at executive-summary level)
- **Outputs:** `state.proposal: Proposal` (markdown sections, no files yet)

### 📦 ExecutorAgent
- **Role:** Packager
- **Responsibility:** Write approved artifacts to disk, build deliverable bundle, log metrics, finalize conversation record
- **Goal:** Produce a single `outputs/<conversation_id>/` folder containing every artifact + `run_summary.json`
- **Tools:** `file_writer` (sandboxed to `outputs/`), `zip_packager`, `metrics_recorder`
- **Inputs:** Validated `state`
- **Outputs:** Filesystem artifacts + `state.run_summary`

---

## 3. Shared state (`AgencyState`)

```python
class AgencyState(BaseModel):
    # Identity
    conversation_id: UUID
    user_id: str
    client_id: str | None

    # Inputs
    audio_path: Path | None
    notes_path: Path | None
    raw_user_message: str | None

    # Agent outputs
    transcript: str | None
    transcript_meta: TranscriptMeta | None
    requirements: Requirements | None
    clarifications: list[Clarification]
    plan: Plan | None
    tasks: list[Task]
    risks: list[Risk]
    proposal: Proposal | None
    validation_report: ValidationReport | None

    # Control
    next_action: str | None
    paused_for_input: bool
    attempt_count: dict[str, int]
    audit_log: list[AuditEntry]   # reasoning + tool calls per agent
    run_summary: RunSummary | None
```

This object **is** the shared memory between agents during a single run.

---

## 4. Graph topology (LangGraph)

```
            START
              │
              ▼
       ┌──────────────┐
       │   Manager    │◄────────────────────────┐
       └──────┬───────┘                         │
              │                                 │ Validator
   ┌──────────┴──────────┐                      │  feedback
   ▼                     ▼                      │
┌──────────────┐   (skip if text)              │
│Transcription │                                │
└──────┬───────┘                                │
       ▼                                         │
┌──────────────┐                                │
│ Requirement  │                                │
└──────┬───────┘                                │
       ▼                                         │
┌──────────────┐  pause for user input         │
│Clarification │──── interrupt ────► [CLI HITL]│
└──────┬───────┘  ◄──── resume ─────           │
       ▼                                         │
┌──────────────┐                                │
│   Planning   │                                │
└──────┬───────┘                                │
       ▼                                         │
┌──────────────┐                                │
│  Task Gen    │                                │
└──────┬───────┘                                │
       ▼                                         │
┌──────────────┐                                │
│     Risk     │                                │
└──────┬───────┘                                │
       ▼                                         │
┌──────────────┐                                │
│   Proposal   │                                │
└──────┬───────┘                                │
       ▼                                         │
┌──────────────┐      reject (max 3)            │
│  Validator   │────────────────────────────────┘
└──────┬───────┘
       │ approve
       ▼
┌──────────────┐
│  Executor    │
└──────┬───────┘
       ▼
      END
```

---

## 5. Reasoning-before-action contract

Every agent node executes in three phases:

```python
async def agent_node(state: AgencyState) -> AgencyState:
    # 1. THINK — produce reasoning trace
    reasoning = await llm.generate(reasoning_prompt(state))
    state.audit_log.append(AuditEntry(agent=NAME, phase="reason", content=reasoning))

    # 2. ACT — call tools / produce structured output
    output = await llm.generate(action_prompt(state, reasoning))
    state.audit_log.append(AuditEntry(agent=NAME, phase="act", content=output))

    # 3. WRITE — merge into shared state + persist message to Postgres
    state = merge_output(state, output)
    await message_repo.append(conversation_id, role="agent", agent=NAME, content=output, reasoning=reasoning)
    return state
```

This satisfies the rubric's "reasoning before action" + "logging of actions and decisions" lines in one mechanism.

---

## 6. Memory — Neon Postgres, ChatGPT-style threads

**Two schemas, same DB:**

### 6.1 Conversation schema (custom)
```sql
conversations(id UUID PK, user_id TEXT, client_id TEXT NULL, title TEXT, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ)
messages(id UUID PK, conversation_id UUID FK, role TEXT, agent_name TEXT NULL, content JSONB, reasoning TEXT NULL, tool_calls JSONB NULL, created_at TIMESTAMPTZ)
conversation_summaries(conversation_id UUID FK, summary TEXT, up_to_message_id UUID, created_at TIMESTAMPTZ)
projects(id UUID PK, conversation_id UUID FK, status TEXT, output_path TEXT, run_summary JSONB)
```

### 6.2 LangGraph checkpoints
- Uses `langgraph-checkpoint-postgres` against the same Neon DB
- Provides pause/resume/replay for graph state
- Schema is auto-managed by the library

### 6.3 Retrieval pattern
1. On session start: load conversation thread (most recent N messages or last summary + tail) → inject as Manager context
2. Per agent: messages are written to DB as they happen; downstream agents see them via shared state (not by re-querying DB)
3. Long threads: when thread length > threshold, summarizer writes a `conversation_summaries` row and prunes older messages from context window

**No vector DB needed.** Conversation-shaped memory + structured state covers all rubric memory requirements.

---

## 7. Tools registry

| Tool | Used by | External? |
|---|---|---|
| `groq_whisper_transcribe` | Transcription | ✅ Groq API |
| `tavily_web_search` | Planning, Risk | ✅ Tavily API |
| `entity_extractor` | Requirement | Local (Groq LLM) |
| `structured_output_parser` | Multiple | Local |
| `template_loader` | Planning, Proposal | Local files |
| `rubric_loader` / `rubric_checker` | Clarification, Validator | Local YAML |
| `contradiction_detector` | Clarification | Local |
| `dag_validator` | Task Gen | Local |
| `calculator` | Risk | Local (safe eval) |
| `file_writer` | Executor | Local FS (sandboxed) |
| `zip_packager` | Executor | Local |
| `hitl_prompt` | Clarification | Local (CLI) |
| `metrics_recorder` | Executor | Local + Postgres |

Each tool is a `@tool`-decorated LangChain tool. Agents receive only their allowed tools at graph build time.

---

## 8. Reusable prompt system

```
src/agencyos/prompts/
├── system/              # one .j2 per agent role
│   ├── manager.j2
│   ├── requirement.j2
│   └── ...
├── partials/            # shared blocks
│   ├── reasoning_rubric.j2
│   ├── output_schema.j2
│   └── retry_context.j2
└── tasks/               # parameterized task prompts
    ├── extract_requirements.j2
    └── ...
```

`PromptRegistry.render(name, **vars)` loads + renders via Jinja2. No prompt is hardcoded in agent code.

---

## 9. Error handling — three layers

| Layer | Mechanism | Max | Fallback |
|---|---|---|---|
| Tool | `@tenacity.retry` (exponential backoff) on external API calls | 3 | Raise to agent |
| Agent | Pydantic validation retry: on parse failure, re-prompt with error injected | 2 | Mark step failed, propagate to Manager |
| Graph | Validator-driven retry: bad output → Manager re-dispatches specialist with feedback | 3 cycles | `ExecutorAgent` emits partial package + `incidents.md` listing failures |

---

## 10. Logging & observability

- **`structlog`** JSON logs to `logs/agencyos.log` — every agent call, tool call, decision, retry
- **`audit_log`** in state — reasoning trace persisted to Postgres as message rows
- **`run_summary.json`** per run — agent calls, token usage, wall time, validator scores, retry counts
- **Optional LangSmith** tracing (env-toggled via `LANGSMITH_API_KEY`)

---

## 11. Measurable results (rubric requirement)

| Metric | How measured | Target |
|---|---|---|
| Time saved | Wall-clock per run vs. manual baseline | ≥ 90% reduction |
| Automation rate | % of runs reaching Executor without HITL escalation | ≥ 70% |
| Quality | Validator score (1–10) across rubric dimensions | ≥ 8.0 avg |
| Token cost | Groq tokens × $/M vs. estimated freelancer cost | Report ratio |
| Clarification recall | % of seeded gaps caught by Clarification Agent | ≥ 90% (held-out benchmark) |

`scripts/benchmark.py` runs the full eval suite on `eval/briefs/*.{txt,mp3}` and emits `benchmarks/report.md`.

---

## 12. Project layout

```
agencyos/
├── pyproject.toml
├── .env.example                 # DATABASE_URL, GROQ_API_KEY, TAVILY_API_KEY, ...
├── .env                         # gitignored
├── alembic.ini
├── ARCHITECTURE.md              # this file
├── README.md
├── migrations/
│   └── versions/
├── docs/
│   ├── architecture.md          # mermaid: high-level arch
│   ├── sequence.md              # mermaid: per-run sequence
│   ├── agent_flow.md            # mermaid: routing
│   └── state_machine.md         # mermaid: state transitions
├── src/agencyos/
│   ├── __init__.py
│   ├── main.py                  # CLI entry
│   ├── config.py                # pydantic-settings
│   ├── llm/                     # Groq client wrapper
│   ├── agents/                  # 11 agent modules + base.py
│   ├── graph/
│   │   ├── state.py             # AgencyState + payload Pydantic models
│   │   ├── builder.py           # graph wiring
│   │   └── routing.py           # Manager / Validator routing fns
│   ├── tools/
│   ├── prompts/
│   ├── memory/
│   │   ├── db.py                # engine + session
│   │   ├── models.py            # SQLModel tables
│   │   ├── repository.py        # load_thread, append_message, summarize
│   │   └── checkpointer.py      # langgraph-checkpoint-postgres wrapper
│   ├── cli/
│   │   └── app.py               # Typer CLI
│   └── observability/
│       ├── logging.py
│       └── run_summary.py
├── eval/
│   └── briefs/                  # seed inputs for benchmarks
├── benchmarks/
├── outputs/                     # gitignored, per-conversation deliverables
├── logs/                        # gitignored
└── tests/
```

---

## 13. Phased build plan (~6–8 weeks)

1. **W1 — Foundation.** Repo scaffold, config, Postgres + Alembic, conversation/message schema, structlog, CLI shell, Groq LLM wrapper, prompt registry, single dummy agent end-to-end.
2. **W2 — Transcription + Requirement + Clarification (HITL).** Audio path + text path; CLI pause/resume loop.
3. **W3 — Planning + TaskGen + Risk.** Tavily wired, structured outputs.
4. **W4 — Validator + retry loop + Proposal.**
5. **W5 — Executor + LangGraph checkpointer + run summary.**
6. **W6 — Benchmarks + Mermaid diagrams.** Measurable-results report.
7. **W7 — Polish + multi-vertical briefs.**
8. **W8 — Buffer / stretch (LangSmith, second integration, web UI prep).**
