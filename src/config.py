"""Centralized runtime configuration loaded from environment / .env."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    groq_api_key: str = Field(...)
    groq_model_manager: str = "llama-3.3-70b-versatile"
    groq_model_specialist: str = "llama-3.3-70b-versatile"
    groq_model_validator: str = "llama-3.3-70b-versatile"
    groq_whisper_model: str = "whisper-large-v3"

    # External integrations
    tavily_api_key: str | None = None

    # ClickUp (ticket creation via MCP). Tickets are created inside a List, so a default
    # list id is needed for bulk pushes; the team/workspace id is required by the MCP server.
    clickup_api_key: str | None = None
    clickup_team_id: str | None = None
    clickup_list_id: str | None = None  # default target List for created tickets
    # The MCP server is launched as a stdio subprocess. Pinned to 0.8.5 — the last release before
    # the server went "freemium" (newer versions paywall multi-workspace tokens, returning a
    # license/"pick a workspace" prompt instead of creating the task). Override to vendor another.
    clickup_mcp_command: str = "npx"
    clickup_mcp_args: str = "-y @taazkareem/clickup-mcp-server@0.8.5"

    # Database
    database_url: str = Field(...)
    database_url_sync: str = Field(...)

    # Observability
    langsmith_api_key: str | None = None
    langsmith_project: str = "agencyos"
    langsmith_tracing: bool = False

    # Runtime
    log_level: str = "INFO"
    output_dir: Path = Path("./outputs")
    max_validator_retries: int = 3
    max_tool_retries: int = 3


settings = Settings()  # type: ignore[call-arg]
