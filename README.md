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
- **Validator** — scores against a rubric; gates the executor.
- **Executor** — packages approved artifacts to `outputs/<conversation_id>/`.

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

## Project status

**Conversational orchestrator working end to end** (offline-tested, 38 tests passing):
intent classification, ask-first prerequisite resolution, dynamic agent dispatch, clarification
HITL, full-pipeline intent, and the CLI `chat` REPL — all on LangGraph interrupts + the Postgres
checkpointer via the UI-agnostic `orchestrator.run_turn`.

Agents currently return **deterministic placeholder outputs** so routing is fully testable without
network. Next phase: implement the real `act()` bodies (Groq structured output, Whisper, Tavily,
file packaging) and the Next.js web UI on top of `run_turn`.

To run against live services, set `GROQ_API_KEY` + Neon `DATABASE_URL` in `.env`, then
`uv run agencyos chat`.
