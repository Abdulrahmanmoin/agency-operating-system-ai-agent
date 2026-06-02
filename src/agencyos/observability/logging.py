"""structlog configuration. JSON to file, pretty to console."""

import logging
import sys
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
    stream_handler = logging.StreamHandler(sys.stderr)

    logging.basicConfig(
        level=settings.log_level,
        format="%(message)s",
        handlers=[file_handler, stream_handler],
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level)
        ),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    _configure()
    return structlog.get_logger(name)
