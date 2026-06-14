"""HTTP API layer — a thin FastAPI wrapper over the UI-agnostic orchestrator.

The web frontend (Next.js) talks to this; it adds no conversation logic of its own. Every turn
goes through `orchestrator.drive_turn` exactly like the CLI, and artifacts are read straight from
the LangGraph checkpoint state. See `agencyos/api/app.py`.
"""

from api.app import app

__all__ = ["app"]
