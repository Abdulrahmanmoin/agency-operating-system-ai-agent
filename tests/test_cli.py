"""CLI smoke tests — drive the `chat` REPL with a mocked session (no DB, no LLM)."""

from contextlib import asynccontextmanager

from typer.testing import CliRunner

from cli.app import app
from orchestrator import TurnResult

runner = CliRunner()


def _fake_session(turn_impl):
    @asynccontextmanager
    async def fake_open_session(conversation_id, **kwargs):  # noqa: ANN001
        yield turn_impl

    return fake_open_session


def test_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "AgencyOS" in result.stdout


def test_chat_loop_offers_capabilities_then_handles_input(monkeypatch):
    calls: list[str | None] = []

    async def turn(user_message=None):  # noqa: ANN001
        calls.append(user_message)
        if user_message is None:
            return TurnResult(kind="message", message="CAPABILITIES MENU")
        return TurnResult(kind="message", message=f"ran something for: {user_message}")

    monkeypatch.setattr("cli.app.open_session", _fake_session(turn))

    result = runner.invoke(app, ["chat", "--user", "me"], input="extract requirements\nexit\n")
    assert result.exit_code == 0
    assert "CAPABILITIES MENU" in result.stdout
    assert "ran something for: extract requirements" in result.stdout
    assert calls == [None, "extract requirements"]


def test_chat_loop_renders_awaiting_question(monkeypatch):
    async def turn(user_message=None):  # noqa: ANN001
        if user_message is None:
            return TurnResult(kind="message", message="MENU")
        if user_message == "draft a proposal":
            return TurnResult(
                kind="awaiting_confirmation",
                question="Run requirement, planning first? (yes/no)",
            )
        return TurnResult(kind="message", message="all done")

    monkeypatch.setattr("cli.app.open_session", _fake_session(turn))

    result = runner.invoke(app, ["chat"], input="draft a proposal\nyes\nexit\n")
    assert result.exit_code == 0
    assert "Run requirement, planning first?" in result.stdout
    assert "all done" in result.stdout
