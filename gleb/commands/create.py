"""CLI command: create."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from gleb.commands.create_utils import run_create
from gleb.core.exceptions import BlenderNotFoundError, BlenderVersionError, GlebError


def create_command(
    output: Path = typer.Argument(
        ...,
        help=(
            "Destination path for the new .blend file. "
            "Parent directory must exist. File is created or overwritten."
        ),
    ),
    asset: list[str] | None = typer.Option(
        None,
        "--asset",
        help=(
            "Seed one root asset collection NAME with visual_NAME/mesh_NAME/layer_1_NAME/ and "
            "static_NAME/trimesh_NAME/tri_layer_1_NAME/ (Collection names are global in Blender). "
            "Repeatable. Omit to create only _support/ (add assets later via Blender or gleb edit)."
        ),
    ),
    pretty: bool = typer.Option(
        False,
        "--pretty",
        help="Render a human-readable Rich terminal view instead of emitting JSON. Use JSON mode (default) when piping to agents or other tools.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        help="Suppress Blender's own stderr output. The JSON result envelope is always written to stdout.",
    ),
    blender: str | None = typer.Option(
        None,
        "--blender",
        help="Path to the Blender 5+ executable. Overrides the BLENDER_PATH env var and PATH lookup.",
    ),
) -> None:
    """Create a new .blend file with the flat Blender → Godot pipeline layout.

    Scene root collections:
      _support/  — prefix '_' marks ignored collections (never exported by gleb export).
      <asset>/   — each non-_ root collection exports as its own <asset>.glb

    Each seeded asset uses unique child names (Blender global collection names):
      <asset>/visual_<asset>/mesh_<asset>/layer_<N>_<asset>/
      <asset>/static_<asset>/trimesh_<asset>/tri_layer_<N>_<asset>/

    See docs/commands/create.md and the climbing_game blender-godot-pipeline.md spec.
    """
    asset_names = [a.strip() for a in (asset or []) if a.strip()]

    def _err(exc: Exception, code: int) -> None:
        typer.echo(
            json.dumps(
                {
                    "meta": {
                        "output": str(output),
                        "command": "create",
                    },
                    "summary": {},
                    "data": {},
                    "warnings": [],
                    "errors": [str(exc)],
                },
                ensure_ascii=True,
            )
        )
        raise typer.Exit(code=code)

    try:
        result = run_create(
            output=output,
            assets=asset_names,
            blender_path=blender,
            quiet=quiet,
        )
    except (BlenderNotFoundError, BlenderVersionError) as exc:
        _err(exc, 3)
        return
    except GlebError as exc:
        _err(exc, 1)
        return

    if pretty:
        _render_create_pretty(result)
    else:
        typer.echo(result.model_dump_json())

    if result.errors:
        raise typer.Exit(code=1)


def _render_create_pretty(result: object) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    console.print(f"[bold green]create[/bold green] {result.meta.output}")  # type: ignore[attr-defined]
    console.print(f"  Blender: {result.meta.blender_version}")  # type: ignore[attr-defined]
    console.print(
        f"  collections: [bold]{result.summary.collections_created}[/bold]"  # type: ignore[attr-defined]
        f"  assets seeded: [bold]{result.summary.assets_created}[/bold]"  # type: ignore[attr-defined]
    )

    if result.data.assets:  # type: ignore[attr-defined]
        console.print("  seeded assets:")
        for name in result.data.assets:  # type: ignore[attr-defined]
            console.print(f"    [cyan]{name}[/cyan]")

    if result.data.collections:  # type: ignore[attr-defined]
        table = Table(show_header=False, box=None, padding=(0, 2))
        for name in result.data.collections:  # type: ignore[attr-defined]
            table.add_row(f"  [dim]{name}[/dim]")
        console.print(table)

    for w in result.warnings:  # type: ignore[attr-defined]
        console.print(f"[yellow]warning:[/yellow] {w}")
    for e in result.errors:  # type: ignore[attr-defined]
        console.print(f"[red]error:[/red] {e}")
