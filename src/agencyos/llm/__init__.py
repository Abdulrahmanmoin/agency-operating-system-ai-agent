"""LLM clients (Groq) + structured-output helpers used across agents."""

from agencyos.llm.groq import get_chat_model

__all__ = ["get_chat_model", "ainvoke_structured"]


async def ainvoke_structured(runnable, messages, *, attempts: int = 3):
    """Invoke a structured-output runnable, retrying transient Groq failures.

    Groq's `function_calling` structured output is schema-accurate but occasionally emits a
    malformed tool-call envelope (`tool_use_failed`) or output the parser rejects. Generation is
    stochastic, so a retry almost always succeeds. Non-transient errors (auth, etc.) propagate.
    """
    from langchain_core.exceptions import OutputParserException

    last_exc: Exception | None = None
    for _ in range(attempts):
        try:
            return await runnable.ainvoke(messages)
        except OutputParserException as exc:
            last_exc = exc
        except Exception as exc:  # noqa: BLE001 — narrow to Groq's transient tool failure
            if "tool_use_failed" in str(exc) or "function" in str(exc).lower():
                last_exc = exc
            else:
                raise
    assert last_exc is not None
    raise last_exc
