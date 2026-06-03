"""Live end-to-end smoke test against Groq + Neon.

Run:  uv run python scripts/live_smoke.py
Exercises: capabilities offer, intent classification, single-agent dispatch, full pipeline,
clarification HITL, and the Postgres checkpointer (state persisted across turns) — all over a
single reused connection via orchestrator.open_session.
"""

import asyncio
import logging
import sys
from uuid import uuid4

# psycopg async needs the selector loop on Windows.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Quiet the noisy library/info logs so the turn output is readable.
logging.disable(logging.INFO)

from agencyos.orchestrator import open_session  # noqa: E402

NOTES = "sample_data/meeting_brightbrew.txt"


def show(label: str, r) -> None:
    print(f"\n>>> {label}")
    print(f"[{r.kind}] {(r.message or r.question or '').strip()}", flush=True)


async def main() -> None:
    cid = uuid4()
    print(f"=== conversation {cid} ===", flush=True)

    async with open_session(cid, user_id="lena", client_id="brightbrew", notes_path=NOTES) as turn:
        show("Turn 1: open with notes, no task", await turn(None))
        show("Turn 2: 'extract the requirements'", await turn("extract the requirements"))

        r = await turn("handle this end to end")
        show("Turn 3: 'handle this end to end'", r)

        if r.awaiting_input:
            show("Turn 4: answered clarification", await turn("mobile-first specialty coffee drinkers"))

    print("\nLIVE TEST OK", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
