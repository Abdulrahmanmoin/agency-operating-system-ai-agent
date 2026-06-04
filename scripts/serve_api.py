"""Launch the AgencyOS HTTP API.

psycopg (LangGraph's Postgres checkpointer) cannot run on Windows' ProactorEventLoop — it needs the
SelectorEventLoop. uvicorn unfortunately *hardcodes* the Proactor loop on Windows (see
uvicorn/loops/asyncio.py), ignoring the event-loop policy. So we don't use `uvicorn.run` /
`python -m uvicorn`; instead we drive uvicorn's Server under our own `asyncio.run`, which honors the
selector policy we set below.

    python scripts/serve_api.py            # serves on http://127.0.0.1:8000
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn  # noqa: E402


def main() -> None:
    config = uvicorn.Config(
        "agencyos.api.app:app",
        host="127.0.0.1",
        port=8000,
        log_level="info",
    )
    server = uvicorn.Server(config)
    # asyncio.run() creates the loop via our selector policy, bypassing uvicorn's Proactor factory.
    asyncio.run(server.serve())


if __name__ == "__main__":
    main()
