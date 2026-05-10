"""CLI command: export."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from gleb.commands.export_utils import run_export
from gleb.core.exceptions import BlenderNotFoundError, BlenderVersionError, GlebError


def export_command(
    blend_file: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        help=(
            "Path to the source .blend file. Root collections whose name starts with '_' are ignored; "
            "every other root collection is one exportable asset."
        ),
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        help=(
            "Directory where .glb files are written. Created if it does not exist. "
            "Defaults to <blend_file_directory>/export/."
        ),
    ),
    asset: list[str] | None = typer.Option(
        None,
        "--asset",
        help=(
            "Export only this root asset collection name. Repeatable for multiple assets. "
            "Omit to export every non-_ root collection."
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
    no_apply_modifiers: bool = typer.Option(
        False,
        "--no-apply-modifiers",
        help=(
            "Pass Blender glTF 'Apply Modifiers' as off. Default applies modifiers (excluding Armatures); "
            "disabling preserves shape keys but leaves stacks un-baked."
        ),
    ),
    no_export_tangents: bool = typer.Option(
        False,
        "--no-export-tangents",
        help="Skip vertex tangents in glTF (default exports tangents for normal-mapped PBR in Godot).",
    ),
    materials: str = typer.Option(
        "EXPORT",
        "--materials",
        help="Blender glTF material mode: EXPORT (full PBR bake), PLACEHOLDER (slots only), VIEWPORT, NONE.",
    ),
) -> None:
    """Export each root asset collection as a separate .glb for Godot import.

    Ignores scene-root collections whose name starts with '_' (e.g. _support).

    Before export, objects under <asset>/visual_<asset>/mesh_<asset>/layer_<N>_<asset>/ receive
    godot_type=mesh and render_layers (bitmask). Objects under
    <asset>/static_<asset>/trimesh_<asset>/tri_layer_<N>_<asset>/ receive collision_trimesh;
    convex_* / cvx_layer_* and box_* / box_layer_* receive collision_convex / collision_box.
    Existing per-object custom properties are not overwritten.

    Collection names embed the asset slug so multiple assets in one file need no Blender .001 suffixes.

    Exit code 1 if any asset export fails; exit code 3 if Blender is missing or too old.
    """
    resolved_output_dir = output_dir or (blend_file.parent / "export")

    def _err(exc: Exception, code: int) -> None:
        typer.echo(
            json.dumps(
                {
                    "meta": {
                        "file": str(blend_file),
                        "output_dir": str(resolved_output_dir),
                        "command": "export",
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
        mat = materials.upper()
        if mat not in {"EXPORT", "PLACEHOLDER", "VIEWPORT", "NONE"}:
            mat = "EXPORT"

        result = run_export(
            blend_file=blend_file,
            output_dir=resolved_output_dir,
            assets=list(asset) if asset else None,
            apply_modifiers=not no_apply_modifiers,
            export_tangents=not no_export_tangents,
            export_materials=mat,
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
        _render_export_pretty(result)
    else:
        typer.echo(result.model_dump_json())

    if result.errors or result.summary.assets_failed > 0:
        raise typer.Exit(code=1)


def _render_export_pretty(result: object) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    console.print(f"[bold green]export[/bold green] {result.meta.file}")  # type: ignore[attr-defined]
    console.print(f"  output dir: {result.meta.output_dir}")  # type: ignore[attr-defined]
    console.print(f"  Blender:    {result.meta.blender_version}")  # type: ignore[attr-defined]
    console.print(
        f"  exported: [bold green]{result.summary.assets_exported}[/bold green]"  # type: ignore[attr-defined]
        f"  skipped: {result.summary.assets_skipped}"  # type: ignore[attr-defined]
        f"  failed: [bold red]{result.summary.assets_failed}[/bold red]"  # type: ignore[attr-defined]
    )

    if result.data.exports:  # type: ignore[attr-defined]
        table = Table(show_header=True, box=None, padding=(0, 2))
        table.add_column("asset")
        table.add_column("status")
        table.add_column("path")
        for entry in result.data.exports:  # type: ignore[attr-defined]
            colour = "green" if entry.status == "exported" else "red"
            table.add_row(
                entry.asset,
                f"[{colour}]{entry.status}[/{colour}]",
                entry.path,
            )
        console.print(table)

    for w in result.warnings:  # type: ignore[attr-defined]
        console.print(f"[yellow]warning:[/yellow] {w}")
    for e in result.errors:  # type: ignore[attr-defined]
        console.print(f"[red]error:[/red] {e}")
