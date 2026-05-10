"""CLI entrypoint for gleb."""

from __future__ import annotations

import typer

from gleb.commands.create import create_command
from gleb.commands.edit import edit_command
from gleb.commands.explore import explore_command
from gleb.commands.export import export_command
from gleb.commands.textures import textures_app

app = typer.Typer(
    help=(
        "CLI for Blender 5+ automation workflows. "
        "Runs Blender in background mode (-b) and communicates via base64-encoded JSON payloads. "
        "Every command emits a single JSON envelope to stdout: "
        "{meta, summary, data, warnings, errors}. "
        "Requires Blender 5+ on PATH or BLENDER_PATH env var."
    )
)


@app.callback()
def root() -> None:
    """Root command group."""


app.command("explore")(explore_command)
app.command("edit")(edit_command)
app.command("create")(create_command)
app.command("export")(export_command)
app.add_typer(textures_app, name="textures")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
