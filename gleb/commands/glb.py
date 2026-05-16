"""CLI command group: `gleb glb` — inspect exported .glb files."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from gleb.commands.glb_utils import run_glb_inspect
from gleb.core.exceptions import GlebError
from gleb.formatters.pretty import render_glb_pretty

glb_app = typer.Typer(
    help=(
        "Inspect exported .glb files (the post-`gleb export` artefact). "
        "Imports each file in a fresh Blender session and reports per-object "
        "metadata: parent, vertices/polygons, glTF extras, UV layers, material "
        "slots, and polygon distribution per material slot."
    )
)


@glb_app.command("show")
def glb_show(
    glb_paths: list[Path] = typer.Argument(
        ...,
        help="One or more .glb files to inspect. Each file is imported into a fresh scene.",
    ),
    pretty: bool = typer.Option(
        False,
        "--pretty",
        help="Render a human-readable Rich terminal view instead of emitting JSON.",
    ),
    quiet: bool = typer.Option(
        True,
        "--quiet/--verbose",
        help="Suppress Blender stderr (default). --verbose forwards Blender output for debugging.",
    ),
) -> None:
    """Inspect one or more .glb files. Output envelope: {meta, summary, data, warnings, errors}."""
    for p in glb_paths:
        if not p.exists():
            typer.echo(
                json.dumps(
                    {
                        "meta": {"command": "glb"},
                        "summary": {},
                        "data": {"inspects": []},
                        "warnings": [],
                        "errors": [f"file not found: {p}"],
                    },
                    ensure_ascii=True,
                )
            )
            raise typer.Exit(code=1)
        if p.suffix.lower() != ".glb":
            typer.echo(
                json.dumps(
                    {
                        "meta": {"command": "glb"},
                        "summary": {},
                        "data": {"inspects": []},
                        "warnings": [],
                        "errors": [f"not a .glb file: {p}"],
                    },
                    ensure_ascii=True,
                )
            )
            raise typer.Exit(code=1)

    try:
        result = run_glb_inspect(list(glb_paths), quiet=quiet)
    except GlebError as exc:
        typer.echo(
            json.dumps(
                {
                    "meta": {"command": "glb"},
                    "summary": {},
                    "data": {"inspects": []},
                    "warnings": [],
                    "errors": [str(exc)],
                },
                ensure_ascii=True,
            )
        )
        raise typer.Exit(code=1) from exc

    if pretty:
        render_glb_pretty(result)
        return
    typer.echo(result.model_dump_json())
