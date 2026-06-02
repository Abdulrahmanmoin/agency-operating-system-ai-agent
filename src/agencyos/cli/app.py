"""AgencyOS CLI — `agencyos` command group."""

from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(help="AgencyOS — multi-agent client-intake automation.", no_args_is_help=True)
console = Console()


@app.command()
def version() -> None:
    """Show the installed AgencyOS version."""
    from agencyos import __version__

    console.print(f"[bold]AgencyOS[/bold] v{__version__}")


@app.command()
def run(
    audio: Path | None = typer.Option(None, "--audio", "-a", help="Path to audio file."),
    notes: Path | None = typer.Option(None, "--notes", "-n", help="Path to notes file (txt/docx/pdf)."),
    user: str = typer.Option("anonymous", "--user", "-u", help="User identifier."),
    client: str | None = typer.Option(None, "--client", "-c", help="Client identifier."),
) -> None:
    """Run the AgencyOS graph end-to-end on an audio or notes input."""
    if audio is None and notes is None:
        console.print("[red]Provide --audio or --notes.[/red]")
        raise typer.Exit(code=1)

    console.print(f"[dim]Starting run for user={user} client={client}[/dim]")
    # TODO: wire to graph.builder.build_graph().compile(checkpointer=...).ainvoke(...)
    console.print("[yellow]Graph execution not yet implemented — scaffolding stage.[/yellow]")


@app.command()
def threads(user: str = typer.Option(..., "--user", "-u")) -> None:
    """List recent conversation threads for a user."""
    console.print(f"[yellow]Thread listing not yet implemented for user={user}.[/yellow]")
