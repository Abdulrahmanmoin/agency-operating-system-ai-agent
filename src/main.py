"""CLI entry point. Delegates to the Typer app in `cli.app`."""

from cli.app import app


def main() -> None:
    app()


if __name__ == "__main__":
    main()
