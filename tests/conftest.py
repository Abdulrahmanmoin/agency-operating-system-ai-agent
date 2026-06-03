"""Test bootstrap: provide stub env vars so `agencyos.config.Settings` loads without real secrets.

These are set before any `agencyos` import so module-level `settings = Settings()` succeeds.
Real values come from `.env` in normal runs; tests never touch external services.
"""

import os

os.environ.setdefault("GROQ_API_KEY", "test-stub-key")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://stub:stub@localhost/stub")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql+psycopg://stub:stub@localhost/stub")
