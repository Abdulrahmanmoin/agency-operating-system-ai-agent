"""Jinja2-backed prompt registry. No hardcoded prompts anywhere else."""

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

_PROMPT_ROOT = Path(__file__).parent

_env = Environment(
    loader=FileSystemLoader(_PROMPT_ROOT),
    autoescape=select_autoescape(disabled_extensions=("j2",), default=False),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render(name: str, **context: Any) -> str:
    """Render a prompt template. `name` is the path under prompts/, e.g. 'system/manager.j2'."""
    return _env.get_template(name).render(**context)
