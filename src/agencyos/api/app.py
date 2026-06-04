"""FastAPI app exposing AgencyOS to a web frontend.

Design: one long-lived Postgres connection + compiled graph per conversation (mirroring the CLI's
`open_session`), cached in-process. Each HTTP turn calls the same `orchestrator.drive_turn` the CLI
uses, so HITL pauses (confirmation / clarification) work identically — the graph stays paused in
Postgres and the user's next message resumes it. Artifacts are read from the live graph state.

Run:  uvicorn agencyos.api.app:app --reload --port 8000
"""

import asyncio
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from uuid import UUID, uuid4

# psycopg's async driver (LangGraph Postgres checkpointer) needs the selector loop on Windows.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, File, HTTPException, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from agencyos import views  # noqa: E402
from agencyos.graph.builder import build_graph  # noqa: E402
from agencyos.graph.state import AgencyState  # noqa: E402
from agencyos.memory.checkpointer import checkpointer_cm  # noqa: E402
from agencyos.orchestrator import drive_turn  # noqa: E402
from agencyos.tools.document_loader import load_document  # noqa: E402

# Where uploaded meeting material is stored (one folder per conversation). Audio must persist so the
# transcription agent can read it on a later turn; notes are loaded to text immediately.
_UPLOAD_ROOT = Path(__file__).resolve().parents[3] / "uploads"
_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".mp4", ".ogg", ".webm", ".flac"}
_NOTES_EXTS = {".txt", ".md", ".text", ".docx", ".pdf"}

# Human-readable titles for the artifact cards the frontend renders.
_ARTIFACT_TITLES = {
    "requirement": "Requirements",
    "clarification": "Clarifications",
    "planning": "Project Plan",
    "task_generation": "Tasks",
    "risk": "Risk Analysis",
    "proposal": "Proposal",
    "validator": "Quality Review",
    "executor": "Saved Package",
}


class _Session:
    """One conversation: a dedicated Postgres connection + compiled graph, kept open across turns."""

    def __init__(self, conversation_id: UUID) -> None:
        self.conversation_id = conversation_id
        self._stack = AsyncExitStack()
        self._lock = asyncio.Lock()  # serialize turns within a conversation
        self.app = None
        self.seed = AgencyState(conversation_id=conversation_id, user_id="web")

    async def start(self) -> None:
        saver = await self._stack.enter_async_context(checkpointer_cm())
        self.app = build_graph().compile(checkpointer=saver)

    async def turn(self, message: str | None):
        async with self._lock:
            return await drive_turn(self.app, self.conversation_id, message, seed=self.seed)

    async def artifacts(self) -> list[dict]:
        cfg = {"configurable": {"thread_id": str(self.conversation_id)}}
        snapshot = await self.app.aget_state(cfg)
        values = snapshot.values or {}
        if not values:
            return []
        try:
            state = AgencyState.model_validate(values)
        except Exception:  # noqa: BLE001 — partial state mid-run; nothing to show yet
            return []
        cards: list[dict] = []
        for name, (render, present) in views._RENDERERS.items():
            if present(state):
                markdown = render(state)
                if markdown:
                    cards.append(
                        {"agent": name, "title": _ARTIFACT_TITLES.get(name, name), "markdown": markdown}
                    )
        return cards

    async def close(self) -> None:
        await self._stack.aclose()


_SESSIONS: dict[UUID, _Session] = {}
_SESSIONS_LOCK = asyncio.Lock()


async def _get_session(conversation_id: UUID) -> _Session:
    session = _SESSIONS.get(conversation_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown conversation. Create one first.")
    return session


app = FastAPI(title="AgencyOS API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemas ───────────────────────────────────────────────────────────


class NewConversationResponse(BaseModel):
    conversation_id: str
    greeting: str | None  # the opening capabilities offer


class MessageRequest(BaseModel):
    message: str


class TurnResponse(BaseModel):
    kind: str  # "message" | "awaiting_confirmation" | "awaiting_clarification"
    message: str | None = None
    question: str | None = None
    awaiting_input: bool = False
    conversation_id: str


class ArtifactsResponse(BaseModel):
    conversation_id: str
    artifacts: list[dict]


class UploadResponse(BaseModel):
    kind: str  # "audio" | "notes"
    filename: str
    message: str  # human-readable note to show in the chat


# ── Routes ────────────────────────────────────────────────────────────


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/api/conversations", response_model=NewConversationResponse)
async def create_conversation() -> NewConversationResponse:
    """Start a fresh conversation and return the opening capabilities offer."""
    conversation_id = uuid4()
    session = _Session(conversation_id)
    await session.start()
    async with _SESSIONS_LOCK:
        _SESSIONS[conversation_id] = session
    opening = await session.turn(None)  # task-less first turn → capabilities menu
    return NewConversationResponse(
        conversation_id=str(conversation_id),
        greeting=opening.message or opening.question,
    )


@app.post("/api/conversations/{conversation_id}/messages", response_model=TurnResponse)
async def send_message(conversation_id: UUID, body: MessageRequest) -> TurnResponse:
    """Send one user turn. Resumes a paused (HITL) graph automatically."""
    session = await _get_session(conversation_id)
    result = await session.turn(body.message)
    return TurnResponse(
        kind=result.kind,
        message=result.message,
        question=result.question,
        awaiting_input=result.awaiting_input,
        conversation_id=str(conversation_id),
    )


@app.get("/api/conversations/{conversation_id}/artifacts", response_model=ArtifactsResponse)
async def get_artifacts(conversation_id: UUID) -> ArtifactsResponse:
    """Current agent outputs (requirements, plan, tasks, risks, proposal, …) as markdown cards."""
    session = await _get_session(conversation_id)
    return ArtifactsResponse(
        conversation_id=str(conversation_id),
        artifacts=await session.artifacts(),
    )


@app.post("/api/conversations/{conversation_id}/upload", response_model=UploadResponse)
async def upload_file(conversation_id: UUID, file: UploadFile = File(...)) -> UploadResponse:
    """Attach meeting material to a conversation.

    Notes (txt/md/docx/pdf) are loaded to text and put in state as `notes_text`; audio
    (mp3/wav/m4a/…) is saved and its path put in state as `audio_path` for the transcription agent.
    The file is merged into the persisted graph state, so the next message sees it.
    """
    session = await _get_session(conversation_id)
    filename = Path(file.filename or "upload").name
    suffix = Path(filename).suffix.lower()

    dest_dir = _UPLOAD_ROOT / str(conversation_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    dest.write_bytes(await file.read())

    cfg = {"configurable": {"thread_id": str(conversation_id)}}

    if suffix in _AUDIO_EXTS:
        await session.app.aupdate_state(cfg, {"audio_path": str(dest)})
        return UploadResponse(
            kind="audio",
            filename=filename,
            message=(
                f"📎 Audio file **{filename}** attached. Ask me to *transcribe it* or "
                "*handle this end to end* to process the meeting."
            ),
        )

    if suffix in _NOTES_EXTS:
        try:
            text = load_document(dest)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=f"Could not read {filename}: {exc}") from exc
        await session.app.aupdate_state(cfg, {"notes_text": text, "notes_path": str(dest)})
        return UploadResponse(
            kind="notes",
            filename=filename,
            message=(
                f"📎 Notes **{filename}** attached ({len(text):,} characters). Ask me to "
                "*extract requirements*, *make a plan*, or *handle this end to end*."
            ),
        )

    raise HTTPException(
        status_code=415,
        detail=f"Unsupported file type '{suffix}'. Use pdf, txt, docx, or audio (mp3/wav/m4a).",
    )


@app.delete("/api/conversations/{conversation_id}")
async def close_conversation(conversation_id: UUID) -> dict:
    """Release a conversation's Postgres connection."""
    async with _SESSIONS_LOCK:
        session = _SESSIONS.pop(conversation_id, None)
    if session is not None:
        await session.close()
    return {"closed": str(conversation_id)}
