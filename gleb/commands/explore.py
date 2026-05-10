"""CLI command: explore."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from gleb.commands.explore_utils import normalize_match, normalize_scope, run_explore
from gleb.core.exceptions import GlebError
from gleb.formatters.pretty import render_explore_pretty


def explore_command(
    blend_file: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        help="Path to the .blend file to inspect. The file is opened read-only — never modified.",
    ),
    scope: str = typer.Option(
        "all",
        "--scope",
        help=(
            "What to report. Valid values: all, scene, collections, objects, materials, modifiers, "
            "animations, relations, constraints, geometry, textures, armatures, libraries, "
            "custom_properties. Default: all."
        ),
    ),
    object_names: list[str] = typer.Option(
        None,
        "--object",
        help=(
            "Filter results to objects whose name matches NAME. "
            "Repeatable for multiple names. Use --match to control comparison mode."
        ),
    ),
    match: str = typer.Option(
        "exact",
        "--match",
        help="Name comparison mode for --object: exact (default), contains, or regex.",
    ),
    ignore_case: bool = typer.Option(
        False,
        "--ignore-case",
        help="Make --object name matching case-insensitive.",
    ),
    detail: bool = typer.Option(
        False,
        "--detail",
        help=(
            "Include verbose per-object data: full modifier settings, world-space transforms, "
            "and constraint parameters. Increases output size significantly."
        ),
    ),
    diagnose: bool = typer.Option(
        False,
        "--diagnose",
        help=(
            "Append a 'diagnose' section with structural and quality findings: "
            "missing UVs, non-manifold geometry, unnamed datablocks, glTF export readiness, etc."
        ),
    ),
    pretty: bool = typer.Option(
        False,
        "--pretty",
        help="Render a human-readable Rich terminal view instead of emitting JSON. Use JSON mode (default) when piping to agents or other tools.",
    ),
) -> None:
    """Read a .blend file and emit a structured JSON report of its contents.

    Output envelope: {"meta": {...}, "summary": {...}, "data": {...}, "warnings": [], "errors": []}.
    Use --scope to narrow the report to a specific category. Use --object to filter by name.
    The source file is never modified.
    """
    try:
        normalized_scope = normalize_scope(scope)
        normalized_match = normalize_match(match)
        names = object_names or []
        result = run_explore(
            blend_file=blend_file,
            scope=normalized_scope,
            object_names=names,
            match=normalized_match,
            ignore_case=ignore_case,
            detail=detail,
            diagnose=diagnose,
        )
    except (ValueError, GlebError) as exc:
        typer.echo(
            json.dumps(
                {
                    "meta": {"file": str(blend_file), "scope": scope},
                    "summary": {},
                    "data": {},
                    "warnings": [],
                    "errors": [str(exc)],
                },
                ensure_ascii=True,
            )
        )
        raise typer.Exit(code=1) from exc

    if pretty:
        render_explore_pretty(result)
        return

    typer.echo(result.model_dump_json())
