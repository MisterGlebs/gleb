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
    bake_uv2: bool = typer.Option(
        False,
        "--bake-uv2/--no-bake-uv2",
        help=(
            "Bake a second UV layer (TEXCOORD_1) inside Blender for Godot LightmapGI. "
            "Pre-applies modifiers (so Array/Mirror produce unique islands), runs "
            "smart_project + average_islands_scale + pack_islands, and stamps a per-mesh "
            "lightmap_texel_size custom property. Bypasses Godot's xatlas fallback."
        ),
    ),
    uv2_method: str = typer.Option(
        "smart",
        "--uv2-method",
        help="UV2 unwrap operator: 'smart' (Smart UV Project, default) or 'lightmap_pack'.",
    ),
    uv2_margin: float = typer.Option(
        0.005,
        "--uv2-margin",
        help=(
            "Island margin in UV space (~ pixels at lightmap resolution; 0.005 "
            "= ~5 px at 1024^2). Used as inter-island gap by the manual packer. "
            "Larger values waste atlas area when there are many islands."
        ),
    ),
    uv2_fill_square: bool = typer.Option(
        False,
        "--uv2-fill-square",
        help=(
            "After smart_project + island layout, uniformly scale the whole UV2 "
            "layout to fill [0,1]^2. Skips average_islands_scale (default runs it "
            "so larger 3D faces get more lightmap texels)."
        ),
    ),
    target_texel_density: float = typer.Option(
        4.0,
        "--target-texel-density",
        help=(
            "Lightmap texels per world meter (default 4.0 -> lightmap_texel_size 0.25). "
            "Per-asset override via custom property on the asset root collection (see "
            "--lightmap-texel-density-prop)."
        ),
    ),
    write_import_sidecar: bool = typer.Option(
        False,
        "--write-import-sidecar",
        help=(
            "Write a Godot <asset>.glb.import file next to each .glb pre-configured for "
            "LightmapGI (Static Lightmaps + lightmap_texel_size). Only writes if the file "
            "does not already exist."
        ),
    ),
    lightmap_texel_density_prop: str = typer.Option(
        "lightmap_texel_density",
        "--lightmap-texel-density-prop",
        help=(
            "Custom-property name read from each asset root collection to override "
            "--target-texel-density per asset. Default 'lightmap_texel_density'."
        ),
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
            bake_uv2=bake_uv2,
            uv2_method=uv2_method,
            uv2_margin=uv2_margin,
            uv2_fill_square=uv2_fill_square,
            target_texel_density=target_texel_density,
            lightmap_texel_density_prop=lightmap_texel_density_prop,
            write_import_sidecar=write_import_sidecar,
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
        show_uv2 = any(
            (entry.uv2_baked_meshes or entry.uv2_skipped_meshes or entry.lightmap_texel_size is not None)
            for entry in result.data.exports  # type: ignore[attr-defined]
        )
        show_sidecar = any(entry.sidecar_path for entry in result.data.exports)  # type: ignore[attr-defined]
        table = Table(show_header=True, box=None, padding=(0, 2))
        table.add_column("asset")
        table.add_column("status")
        if show_uv2:
            table.add_column("uv2")
            table.add_column("texel_size")
        if show_sidecar:
            table.add_column("sidecar")
        table.add_column("path")
        for entry in result.data.exports:  # type: ignore[attr-defined]
            colour = "green" if entry.status == "exported" else "red"
            row = [entry.asset, f"[{colour}]{entry.status}[/{colour}]"]
            if show_uv2:
                row.append(f"{entry.uv2_baked_meshes}b/{entry.uv2_skipped_meshes}s")
                row.append(
                    f"{entry.lightmap_texel_size:.4f}" if entry.lightmap_texel_size is not None else "-"
                )
            if show_sidecar:
                row.append("yes" if entry.sidecar_path else "-")
            row.append(entry.path)
            table.add_row(*row)
        console.print(table)

    for w in result.warnings:  # type: ignore[attr-defined]
        console.print(f"[yellow]warning:[/yellow] {w}")
    for e in result.errors:  # type: ignore[attr-defined]
        console.print(f"[red]error:[/red] {e}")
