"""structlog configuration. JSON logs go to a file; the console stays clean for the CLI."""

import logging
from pathlib import Path

import structlog

from agencyos.config import settings

_configured = False


def _configure() -> None:
    global _configured
    if _configured:
        return

    log_path = Path("logs")
    log_path.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(log_path / "agencyos.log", encoding="utf-8")

    # File-only: keeps agent/tool traces out of the interactive CLI. Inspect logs/agencyos.log.
    logging.basicConfig(
        level=settings.log_level,
        format="%(message)s",
        handlers=[file_handler],
    )
    # Third-party INFO chatter (HTTP requests, etc.) → file only, and only warnings+.
    for noisy in ("httpx", "httpcore", "groq", "langgraph", "langchain"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        # Route through stdlib logging so logs obey the file-only handler above (structlog's
        # default factory writes straight to stdout, which would clutter the interactive CLI).
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level)
        ),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    _configure()
    return structlog.get_logger(name)
