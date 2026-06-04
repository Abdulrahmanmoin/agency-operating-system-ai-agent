"""AgencyOS CLI — `agencyos` command group.

The CLI is just a *driver* for the UI-agnostic `orchestrator.run_turn`: it reads stdin and
prints; all conversation logic lives in the graph + orchestrator. A future Next.js/FastAPI
backend reuses `run_turn` identically (no `input()` there — the pausing lives in the graph).
"""

import asyncio
import sys
import warnings
from pathlib import Path
from uuid import UUID, uuid4

import typer
from rich.console import Console
from rich.markdown import Markdown

from agencyos.orchestrator import open_session

# Keep the interactive console clean: hide LangGraph's msgpack "unregistered type" notice.
warnings.filterwarnings("ignore", message=".*nregistered type.*")

# psycopg's async driver (used by the LangGraph Postgres checkpointer) cannot run on Windows'
# default ProactorEventLoop — it requires the selector loop. Set the policy before any asyncio.run.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

app = typer.Typer(help="AgencyOS - multi-agent client-intake automation.", no_args_is_help=True)
console = Console()

_EXIT_WORDS = {"exit", "quit", ":q", "bye"}


@app.command()
def version() -> None:
    """Show the installed AgencyOS version."""
    from agencyos import __version__

    console.print(f"[bold]AgencyOS[/bold] v{__version__}")


def _print_assistant(text: str | None) -> None:
    if text:
        console.print()
        console.print(Markdown(text))
        console.print()


@app.command()
def chat(
    user: str = typer.Option("anonymous", "--user", "-u", help="User identifier."),
    client: str | None = typer.Option(None, "--client", "-c", help="Client identifier."),
    audio: Path | None = typer.Option(None, "--audio", "-a", help="Audio file (mp3/wav/mp4)."),
    notes: Path | None = typer.Option(None, "--notes", "-n", help="Notes file (txt/docx/pdf)."),
    conversation: str | None = typer.Option(
        None, "--conversation", help="Resume an existing conversation id."
    ),
) -> None:
    """Start (or resume) an interactive AgencyOS conversation."""
    cid = UUID(conversation) if conversation else uuid4()

    async def _loop() -> None:
        console.print(f"[dim]AgencyOS chat — conversation {cid}[/dim]")
        console.print("[dim]Connecting…  (first connect can take ~30s if the DB is asleep)[/dim]")

        # One Postgres connection for the whole conversation (see orchestrator.open_session).
        async with open_session(
            cid,
            user_id=user,
            client_id=client,
            audio_path=str(audio) if audio else None,
            notes_path=str(notes) if notes else None,
        ) as turn:
            console.print("[dim]Connected. Type 'exit' to quit.[/dim]")
            res = await turn(None)  # opening turn → capabilities offer
            _print_assistant(res.message or res.question)

            while True:
                try:
                    user_input = console.input("[bold cyan]you ›[/bold cyan] ").strip()
                except (EOFError, KeyboardInterrupt):
                    console.print("\n[dim]Bye.[/dim]")
                    return
                if user_input.lower() in _EXIT_WORDS:
                    console.print("[dim]Bye.[/dim]")
                    return
                if not user_input:
                    continue

                res = await turn(user_input)
                _print_assistant(res.message or res.question)

    asyncio.run(_loop())


@app.command()
def run(
    user: str = typer.Option("anonymous", "--user", "-u"),
    client: str | None = typer.Option(None, "--client", "-c"),
    audio: Path | None = typer.Option(None, "--audio", "-a"),
    notes: Path | None = typer.Option(None, "--notes", "-n"),
) -> None:
    """One-shot full pipeline: process an input end to end and print the result."""
    if audio is None and notes is None:
        console.print("[red]Provide --audio or --notes.[/red]")
        raise typer.Exit(code=1)

    cid = uuid4()

    async def _once() -> None:
        async with open_session(
            cid,
            user_id=user,
            client_id=client,
            audio_path=str(audio) if audio else None,
            notes_path=str(notes) if notes else None,
        ) as turn:
            await turn(None)  # seed inputs
            res = await turn("handle this end to end")
            _print_assistant(res.message or res.question)

    asyncio.run(_once())
