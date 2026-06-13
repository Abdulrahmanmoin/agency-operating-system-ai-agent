# AgencyOS

> Multi-agent AI system that turns client meeting recordings or notes into a validated, packaged project proposal — autonomously, with full reasoning traceability.

Built with **Python · LangChain · LangGraph · Groq · Neon Postgres** — CLI-first.

See **[ARCHITECTURE.md](./ARCHITECTURE.md)** for the canonical specification.

---

## Quick start

```bash
# 1. Install dependencies (uses uv)
uv sync

# 2. Configure secrets
cp .env.example .env
# edit .env — set GROQ_API_KEY, TAVILY_API_KEY, DATABASE_URL (Neon)

# 3. Apply DB migrations
uv run alembic upgrade head

# 4. Run a project
uv run agencyos run --audio path/to/meeting.mp3 --user you --client acme
# or
uv run agencyos run --notes path/to/notes.txt --user you --client acme
```

## What it does

A client meeting (audio or notes) goes in. AgencyOS is **conversational and intent-driven** — not
a fixed pipeline. You drop in a transcript and it offers what it can do; you ask in plain language
and the **Manager** classifies your intent and runs **only the agents needed**:

- **Manager** — interprets your request, routes, asks before running missing prerequisites.
- **Transcription** — audio → text via Groq Whisper (only if you upload audio).
- **Requirement Analysis** — extracts goals, services, deadlines, budget, constraints.
- **Clarification** — flags critical gaps and **pauses for your input** (HITL).
- **Planning** — phased roadmap and milestones.
- **Task Generation** — Jira-style tasks with priorities and dependencies.
- **Risk Analysis** — deadline / budget / scope risks.
- **Proposal** — client-facing documents.
- **Validator** — scores the package against a rubric; on a fail, sends one agent back to revise (self-correcting loop), then approves.
- **ClickUp** — creates tickets from the generated tasks or a free-form request, **after you confirm** (via the ClickUp MCP server).

Ask for one thing (*"extract the requirements"*), several (*"plan it and flag the risks"*), or the
whole thing (*"handle this end to end"*). If you request something whose inputs aren't ready (e.g. a
proposal before requirements exist), the Manager **asks first** before chaining the prerequisites.

Every agent emits a **reasoning trace** before acting (THINK → ACT → WRITE), recorded in the audit
log. State persists across turns in **Neon Postgres** via the LangGraph checkpointer — pause, resume,
and replay any conversation. The chat thread *is* the memory — ChatGPT-style, no separate vector DB.

Try it: `uv run agencyos chat --user you --notes meeting.txt`

## Why multi-agent

See [ARCHITECTURE.md §1](./ARCHITECTURE.md#1-why-multiple-agents-not-a-single-llm) for the side-by-side comparison.

## Diagrams

- High-level architecture: [docs/architecture.md](./docs/architecture.md)
- Per-run sequence: [docs/sequence.md](./docs/sequence.md)
- Agent state machine: [docs/agent_flow.md](./docs/agent_flow.md)

## ClickUp ticket creation

Ask in plain language and AgencyOS will create ClickUp tickets — after showing you the drafts and
waiting for your **yes**:

- *"Create a ticket to call the client Friday"* → one ad-hoc ticket.
- *"Push all the tasks to ClickUp"* (after task generation ran) → one ticket per task.

It talks to a **ClickUp MCP server** (`langchain-mcp-adapters` → `npx @taazkareem/clickup-mcp-server`,
needs Node). Set these in `.env` (see `.env.example`):

```bash
CLICKUP_API_KEY=pk_...   # ClickUp → Settings → Apps → API Token
CLICKUP_TEAM_ID=...      # the number in your app.clickup.com/<TEAM_ID>/ URL
CLICKUP_LIST_ID=...      # the List new tickets go into (List → ⋯ → Copy ID)
```

Until those are set, the agent says ClickUp isn't connected instead of failing.

## Project status

**Working end to end** (offline-tested, **87 tests passing**): real agent `act()` bodies (Groq
structured output, Whisper transcription, Tavily search), intent classification, ask-first
prerequisite resolution, dynamic dispatch, clarification + ClickUp HITL, the validator self-correction
loop, a Next.js web UI + FastAPI layer (chat, Deliverables panel, file upload, DOCX/PDF download),
and ClickUp ticket creation via MCP — all on LangGraph interrupts + the Postgres checkpointer via the
UI-agnostic `orchestrator.drive_turn`.

To run against live services, set `GROQ_API_KEY` + Neon `DATABASE_URL` (and optionally `TAVILY_API_KEY`
/ ClickUp keys) in `.env`, then `uv run agencyos chat`.
