# What the Agency Agent can do

A multi-agent system that turns a messy client conversation into a validated project package,
pushes the work into ClickUp, and reports real delivery progress back to the PM. You talk to it in
plain language; a **Manager** agent reads your intent and runs only the agents needed.

---

## The agents (capabilities)

### Manager — Chief of Staff (orchestrator)
- Interprets your request and routes it to the right specialist(s).
- Runs **only the agents needed** — not a fixed pipeline.
- Auto-detects missing prerequisites and **asks before** chaining them
  (e.g. you ask for a proposal before requirements exist).
- Handles validator feedback and decides when the job is done.

### Transcription — Audio-to-text
- Converts an uploaded audio recording (mp3/wav/m4a/…) into a clean transcript (Groq Whisper).
- Runs only when you upload audio.
- Prompts: `transcribe it`

### Requirement — Brief decoder
- Extracts client goals, services, deadline, budget, constraints, priorities, and target audience
  from messy notes/transcript into a structured Requirements object.
- Prompts: `extract the requirements`

### Clarification — Gap finder
- Detects vague, missing, or contradictory requirements.
- **Pauses and asks you** the critical questions before planning (human-in-the-loop).
- Prompts: `what's unclear?` · `what should I ask the client?`

### Planning — Strategist
- Builds a phased roadmap: objectives, execution strategy, milestones (with owner, duration,
  deliverables, dependencies), and success metrics.
- Prompts: `make a plan` · `build a phased project plan`

### Task Generation — Project decomposer
- Breaks each milestone into actionable tasks with priorities and dependencies.
- Prompts: `break it into tasks` · `generate tasks with priorities and dependencies`

### Risk — Risk auditor
- Flags unrealistic deadlines, unclear scope, budget mismatches, and bottlenecks — each with a
  severity and a mitigation.
- Prompts: `what are the risks?` · `flag the risks`

### Proposal — Client communicator
- Drafts a client-facing proposal: executive summary, approach, scope, deliverables, timeline,
  investment, key considerations/assumptions, and next steps.
- Prompts: `draft a proposal` · `write a client-ready proposal`

### Validator — QA reviewer
- Scores the package against a rubric for consistency, duplicates, logic, and missing deliverables.
- On a fail, sends **one specific agent** back to revise (self-correcting loop), then approves.
- Prompts: `validate it` · `check it for consistency`

### ClickUp — Delivery coordinator
- Creates ClickUp tickets from the generated tasks **or** from a free-form request.
- Shows you the drafts and **waits for your confirmation** before writing anything.
- Can also update an existing ticket you refer to.
- Talks to a ClickUp MCP server.
- Prompts: `create ClickUp tickets for these tasks` · `create a ticket to call the client Friday`

### Progress Report — Delivery analyst (read-only)
- Joins each ClickUp ticket to the GitHub branch/PR that delivers it (by the `CU-<id>` in the
  branch name) and derives a status: done (PR merged) / in progress (code pushed or PR open) /
  not started.
- Reports overall **% complete**, a per-developer breakdown, what's waiting on merge, recommended
  next actions, and **ClickUp-vs-GitHub mismatches** (e.g. marked complete but no code shipped).
- Prompts: `generate a progress report for the PM` · `show me a progress report`

### Do it all
- Runs the whole intake chain end-to-end (requirements → clarification → planning → tasks → risks
  → proposal → validator).
- Prompts: `handle this end to end` · `do everything`

---

## System-level features

- **Conversational & intent-driven** — ask for one thing, several, or the whole pipeline.
- **Human-in-the-loop** — Clarification and ClickUp pause for your input/approval, then resume.
- **Persistent memory** — every conversation's state lives in Neon Postgres (LangGraph
  checkpointer); pause, resume, and continue any chat across turns and restarts.
- **Reasoning traceability** — each agent emits a THINK → ACT → WRITE trace into an audit log.
- **File upload** — attach meeting audio (mp3/wav/m4a/…) or notes (pdf/txt/docx/md).
- **Deliverables** — requirements, plan, tasks, risks, proposal, quality review, and progress
  report appear as cards, each downloadable as **DOCX or PDF**.
- **Web chat UI** — Next.js chat with a collapsible **chat-history sidebar** (old chats), a
  collapsible **Deliverables** panel, file upload, and downloads, over a FastAPI backend.

---

## Built-in tools the agents use

- **Groq** LLMs (reasoning + structured output) and **Whisper** (transcription)
- **Tavily** web search
- **Document loader** (pdf/docx/txt → text)
- **GitHub** REST (read-only — branches & pull requests)
- **ClickUp** MCP server (ticket creation) + ClickUp REST (read-only status/members)
