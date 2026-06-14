"""UI-agnostic turn runner — the single entry point the CLI and the future Next.js/FastAPI
backend both call. It owns: resume-vs-new-turn detection, graph invocation, and translating
LangGraph interrupts into a `TurnResult` the UI can render.

The conversation engine lives entirely here + in the graph; no UI logic leaks in. The CLI just
reads stdin and prints; a web backend would map HTTP requests to `run_turn` the same way.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from langgraph.types import Command

from graph.builder import build_graph
from graph.state import AgencyState

TurnKind = Literal["message", "awaiting_confirmation", "awaiting_clarification"]


@dataclass
class TurnResult:
    kind: TurnKind
    message: str | None = None  # assistant text to display
    question: str | None = None  # set when awaiting_* — the prompt to put to the user
    payload: dict[str, Any] = field(default_factory=dict)  # raw interrupt value / extras
    conversation_id: str = ""

    @property
    def awaiting_input(self) -> bool:
        return self.kind != "message"


def _config(conversation_id: str | UUID) -> dict:
    return {"configurable": {"thread_id": str(conversation_id)}}


def _to_turn_result(result: dict, conversation_id: str) -> TurnResult:
    """Translate a raw graph `ainvoke` result into a TurnResult."""
    interrupts = result.get("__interrupt__")
    if interrupts:
        value = interrupts[0].value or {}
        raw_kind = value.get("kind", "confirmation")
        kind: TurnKind = (
            "awaiting_clarification" if raw_kind == "clarification" else "awaiting_confirmation"
        )
        return TurnResult(
            kind=kind,
            message=None,
            question=value.get("question"),
            payload=value,
            conversation_id=conversation_id,
        )
    return TurnResult(
        kind="message",
        message=result.get("last_assistant_message"),
        conversation_id=conversation_id,
    )


async def drive_turn(
    app: Any,
    conversation_id: str | UUID,
    user_message: str | None,
    *,
    seed: AgencyState | None = None,
) -> TurnResult:
    """Run one turn against an already-compiled graph `app`.

    Pure of any checkpointer choice — tests drive this with a MemorySaver-compiled app.
    Decides whether to start a new turn, continue an existing thread, or resume an interrupt.
    """
    cfg = _config(conversation_id)
    snapshot = await app.aget_state(cfg)

    if snapshot.next:  # graph is paused at an interrupt → resume
        result = await app.ainvoke(Command(resume=user_message), cfg)
    elif snapshot.created_at is None:  # brand-new thread → seed full state
        if seed is None:
            seed = AgencyState(conversation_id=UUID(str(conversation_id)), user_id="anonymous")
        seed.last_user_message = user_message
        result = await app.ainvoke(seed, cfg)
    else:  # existing thread, not paused → new message merged into persisted state
        result = await app.ainvoke(
            {"last_user_message": user_message, "last_assistant_message": None}, cfg
        )

    return _to_turn_result(result, str(conversation_id))


def _seed_state(
    conversation_id: str | UUID,
    *,
    user_id: str,
    client_id: str | None,
    audio_path: str | None,
    notes_path: str | None,
) -> AgencyState:
    # Load notes text up front so agents have working material from turn one. Audio is
    # transcribed later by the transcription agent.
    notes_text: str | None = None
    if notes_path:
        from tools.document_loader import load_document

        notes_text = load_document(notes_path)

    return AgencyState(
        conversation_id=UUID(str(conversation_id)),
        user_id=user_id,
        client_id=client_id,
        audio_path=Path(audio_path) if audio_path else None,
        notes_path=Path(notes_path) if notes_path else None,
        notes_text=notes_text,
    )


# Type of the per-turn callable yielded by `open_session`.
TurnFn = Callable[[str | None], Awaitable[TurnResult]]


@asynccontextmanager
async def open_session(
    conversation_id: str | UUID,
    *,
    user_id: str = "anonymous",
    client_id: str | None = None,
    audio_path: str | None = None,
    notes_path: str | None = None,
) -> AsyncIterator[TurnFn]:
    """Open ONE Postgres connection + compiled graph for a whole conversation and yield a
    `turn(user_message)` callable. Reusing a single connection across turns avoids per-turn
    Neon reconnects (cold starts / pooler churn). This is what the CLI `chat` REPL uses.
    """
    from memory.checkpointer import checkpointer_cm

    seed = _seed_state(
        conversation_id,
        user_id=user_id,
        client_id=client_id,
        audio_path=audio_path,
        notes_path=notes_path,
    )
    async with checkpointer_cm() as saver:
        app = build_graph().compile(checkpointer=saver)

        async def turn(user_message: str | None) -> TurnResult:
            return await drive_turn(app, conversation_id, user_message, seed=seed)

        yield turn


async def run_turn(
    conversation_id: str | UUID,
    user_message: str | None = None,
    *,
    user_id: str = "anonymous",
    client_id: str | None = None,
    audio_path: str | None = None,
    notes_path: str | None = None,
) -> TurnResult:
    """One-shot entry point: drive a single turn with its own Postgres connection.

    Convenient for scripts/tests and stateless web handlers. Interactive callers should prefer
    `open_session` to reuse one connection across the conversation.
    """
    async with open_session(
        conversation_id,
        user_id=user_id,
        client_id=client_id,
        audio_path=audio_path,
        notes_path=notes_path,
    ) as turn:
        return await turn(user_message)
