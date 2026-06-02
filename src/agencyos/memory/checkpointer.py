"""LangGraph Postgres checkpointer wrapper — gives the graph pause/resume/replay."""

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from agencyos.config import settings


async def get_checkpointer() -> AsyncPostgresSaver:
    # Strip the "+asyncpg" driver suffix — langgraph-checkpoint-postgres expects raw postgresql://
    conn_str = settings.database_url.replace("+asyncpg", "").replace("+psycopg", "")
    saver = AsyncPostgresSaver.from_conn_string(conn_str)
    await saver.setup()
    return saver
