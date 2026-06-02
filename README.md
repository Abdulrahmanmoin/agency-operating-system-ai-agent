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

A client meeting (audio or notes) goes in. Eleven agents collaborate:

1. **Manager** orchestrates and routes.
2. **Transcription** converts audio → text via Groq Whisper.
3. **Requirement Analysis** extracts goals, services, deadlines, budget, constraints.
4. **Clarification** flags gaps and pauses for human input (HITL).
5. **Planning** builds the phased roadmap.
6. **Task Generation** decomposes into Jira-style tasks with dependencies.
7. **Risk Analysis** surfaces deadline/budget/scope risks.
8. **Proposal** drafts client-facing documents.
9. **Validator** scores everything against a rubric — sends work back for retry if it fails.
10. **Executor** packages approved artifacts to `outputs/<conversation_id>/` and a `.zip`.

Every agent emits a **reasoning trace** before acting, persisted as message rows in Neon Postgres alongside the artifacts. The conversation thread *is* the memory — no separate vector DB, ChatGPT-style.

## Why multi-agent

See [ARCHITECTURE.md §1](./ARCHITECTURE.md#1-why-multiple-agents-not-a-single-llm) for the side-by-side comparison.

## Diagrams

- High-level architecture: [docs/architecture.md](./docs/architecture.md)
- Per-run sequence: [docs/sequence.md](./docs/sequence.md)
- Agent state machine: [docs/agent_flow.md](./docs/agent_flow.md)

## Project status

Skeleton complete: state schema, graph topology, agent base class, all 11 agent stubs, tools, memory layer, CLI, observability, tests. Agent `act()` implementations land next.
