"""LLM clients (Groq) + structured-output helpers used across agents."""

from agencyos.llm.groq import get_chat_model

__all__ = ["get_chat_model", "ainvoke_structured"]


def _is_transient(exc: Exception) -> bool:
    """Whether an exception is worth retrying: Groq's malformed tool envelope, a parser
    rejection, or a transient network/connection error (DNS blip, dropped socket, timeout)."""
    text = str(exc).lower()
    if "tool_use_failed" in text or "function" in text:
        return True
    # Network/connection problems are surfaced by httpx/groq under several class names; match by
    # name so we don't hard-import optional internals.
    transient_names = {
        "APIConnectionError",
        "APITimeoutError",
        "ConnectError",
        "ConnectTimeout",
        "ReadTimeout",
        "ReadError",
        "RemoteProtocolError",
        "InternalServerError",  # Groq 5xx
        "RateLimitError",  # Groq 429
    }
    cls = type(exc).__name__
    if cls in transient_names:
        return True
    return "getaddrinfo failed" in text or "connection error" in text or "timed out" in text


async def ainvoke_structured(runnable, messages, *, attempts: int = 3):
    """Invoke a structured-output runnable, retrying transient Groq/network failures.

    Groq's `function_calling` structured output is schema-accurate but occasionally emits a
    malformed tool-call envelope (`tool_use_failed`) or output the parser rejects. Generation is
    stochastic, so a retry almost always succeeds. Transient network errors (DNS blips, dropped
    sockets, Groq 5xx/429) are likewise retried with a short backoff. Non-transient errors
    (auth, bad request, etc.) propagate immediately.
    """
    import asyncio

    from langchain_core.exceptions import OutputParserException

    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return await runnable.ainvoke(messages)
        except OutputParserException as exc:
            last_exc = exc
        except Exception as exc:  # noqa: BLE001 — re-raise anything not transient
            if not _is_transient(exc):
                raise
            last_exc = exc
        if attempt < attempts - 1:
            await asyncio.sleep(0.75 * (attempt + 1))  # 0.75s, 1.5s backoff
    assert last_exc is not None
    raise last_exc
