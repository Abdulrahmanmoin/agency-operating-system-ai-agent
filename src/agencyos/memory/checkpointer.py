"""LangGraph Postgres checkpointer — gives the conversational graph pause/resume/replay.

`AsyncPostgresSaver.from_conn_string` is an *async context manager*, so callers must use it
within `async with checkpointer_cm() as saver:`. Table setup runs once per process.
"""

import warnings
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from agencyos.config import settings

# Our AgencyState carries Pydantic/enum types; LangGraph round-trips them fine but emits a
# noisy "Deserializing unregistered type" warning. Silence just that message.
warnings.filterwarnings("ignore", message="Deserializing unregistered type")

_setup_done = False


def _conn_str() -> str:
    # langgraph-checkpoint-postgres runs on psycopg and wants a raw postgresql:// DSN with
    # libpq-style params (sslmode, channel_binding). Derive it from the psycopg (sync) URL,
    # which already uses those params — NOT from the asyncpg URL whose SSL syntax differs.
    dsn = settings.database_url_sync.replace("+psycopg", "").replace("+asyncpg", "")
    # Fail fast instead of blocking forever if Neon is cold/unreachable or the pooler is busy.
    if "connect_timeout=" not in dsn:
        dsn += ("&" if "?" in dsn else "?") + "connect_timeout=15"
    return dsn


@asynccontextmanager
async def checkpointer_cm() -> AsyncIterator[AsyncPostgresSaver]:
    """Yield an initialized AsyncPostgresSaver. Creates checkpoint tables once per process."""
    global _setup_done
    async with AsyncPostgresSaver.from_conn_string(_conn_str()) as saver:
        if not _setup_done:
            await saver.setup()
            _setup_done = True
        yield saver
