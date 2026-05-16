"""CLI command: compare two .blend files via explore snapshots, or two .glb files / dirs of .glb files."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from gleb.commands.explore_utils import normalize_match, normalize_scope, run_explore
from gleb.commands.glb_utils import is_glb_compare_pair, run_glb_compare
from gleb.core.exceptions import GlebError
from gleb.core.json_diff import diff_any, flatten_diff_paths
from gleb.formatters.pretty import render_compare_pretty, render_glb_compare_pretty
from gleb.models.compare_schema import (
    CompareChanges,
    CompareDataPayload,
    CompareMeta,
    CompareResult,
    CompareSummaryStats,
)
from gleb.models.explore_schema import ExploreResult


def _build_compare_result(left: ExploreResult, right: ExploreResult) -> CompareResult:
    left_dump = left.model_dump()
    right_dump = right.model_dump()
    summary_diff = diff_any(left_dump["summary"], right_dump["summary"])
    explore_diff = diff_any(left_dump["data"], right_dump["data"])

    paths: list[str] = []
    if summary_diff is not None:
        paths.extend(flatten_diff_paths(summary_diff, "summary"))
    if explore_diff is not None:
        paths.extend(flatten_diff_paths(explore_diff, "explore_data"))

    identical = summary_diff is None and explore_diff is None

    meta = CompareMeta(
        left_file=left.meta.file,
        right_file=right.meta.file,
        left_blender_version=left.meta.blender_version,
        right_blender_version=right.meta.blender_version,
        scope=left.meta.scope,
        query=left.meta.query,
        identical=identical,
    )
    stats = CompareSummaryStats(changed_paths=len(paths), paths=paths)
    changes = CompareChanges(summary=summary_diff, explore_data=explore_diff)
    warnings: list[str] = []
    warnings.extend(f"left: {w}" for w in left.warnings)
    warnings.extend(f"right: {w}" for w in right.warnings)

    return CompareResult(
        meta=meta,
        summary=stats,
        data=CompareDataPayload(changes=changes),
        warnings=warnings,
        errors=[],
    )


def compare_command(
    left: Path = typer.Argument(
        ...,
        exists=True,
        help=(
            "Baseline. Either a .blend file (opened read-only via explore) OR a .glb "
            "file OR a directory of .glb files (inspected via the glb probe)."
        ),
    ),
    right: Path = typer.Argument(
        ...,
        exists=True,
        help=(
            "Comparison. Same kind as `left` (mixing .blend with .glb is rejected). "
            "Two directories pair their .glb files by basename."
        ),
    ),
    scope: str = typer.Option(
        "all",
        "--scope",
        help=(
            "What to report — same as gleb explore: all, scene, collections, objects, "
            "materials, modifiers, animations, relations, constraints, geometry, textures, "
            "armatures, libraries, custom_properties. Default: all."
        ),
    ),
    object_names: list[str] | None = typer.Option(
        None,
        "--object",
        help="Filter by object name (repeatable). Same semantics as gleb explore.",
    ),
    match: str = typer.Option(
        "exact",
        "--match",
        help="Name comparison mode for --object: exact (default), contains, or regex.",
    ),
    ignore_case: bool = typer.Option(
        False,
        "--ignore-case",
        help="Case-insensitive --object matching.",
    ),
    detail: bool = typer.Option(
        False,
        "--detail",
        help="Verbose per-object/probe data — same as gleb explore.",
    ),
    diagnose: bool = typer.Option(
        False,
        "--diagnose",
        help="Include diagnose sections — same as gleb explore.",
    ),
    pretty: bool = typer.Option(
        False,
        "--pretty",
        help="Human-readable Rich output instead of JSON.",
    ),
) -> None:
    """Compare two .blend files (via explore snapshot) OR two .glb files / two directories of .glbs.

    Mode is chosen from the file types of the arguments. Exit code 0 only when
    the two sides match; otherwise 1 (including probe failures). Left/right map
    to baseline vs candidate ordering.

    Examples:
      gleb compare a.blend b.blend                  # blend ↔ blend (existing behavior)
      gleb compare baseline.glb candidate.glb       # single-glb diff
      gleb compare exports/baseline exports/candidate  # pairs .glb files by basename
    """
    if is_glb_compare_pair(left, right):
        try:
            glb_result = run_glb_compare(left, right)
        except GlebError as exc:
            typer.echo(
                json.dumps(
                    {
                        "meta": {"left": str(left), "right": str(right), "command": "compare-glb"},
                        "summary": {},
                        "data": {"pairs": []},
                        "warnings": [],
                        "errors": [str(exc)],
                    },
                    ensure_ascii=True,
                )
            )
            raise typer.Exit(code=1) from exc

        if pretty:
            render_glb_compare_pretty(glb_result)
        else:
            typer.echo(glb_result.model_dump_json())

        if glb_result.errors or not glb_result.meta.identical:
            raise typer.Exit(code=1)
        return

    if left.is_dir() or right.is_dir():
        typer.echo(
            json.dumps(
                {
                    "meta": {"left": str(left), "right": str(right)},
                    "summary": {},
                    "data": {},
                    "warnings": [],
                    "errors": [
                        "compare: directories are only supported when both contain .glb files. "
                        "Pass two .blend files for the explore-based diff."
                    ],
                },
                ensure_ascii=True,
            )
        )
        raise typer.Exit(code=1)

    if left.suffix.lower() == ".glb" or right.suffix.lower() == ".glb":
        typer.echo(
            json.dumps(
                {
                    "meta": {"left": str(left), "right": str(right)},
                    "summary": {},
                    "data": {},
                    "warnings": [],
                    "errors": ["compare: cannot mix .blend and .glb arguments."],
                },
                ensure_ascii=True,
            )
        )
        raise typer.Exit(code=1)

    names = object_names or []
    try:
        normalized_scope = normalize_scope(scope)
        normalized_match = normalize_match(match)
        left_explore = run_explore(
            blend_file=left,
            scope=normalized_scope,
            object_names=names,
            match=normalized_match,
            ignore_case=ignore_case,
            detail=detail,
            diagnose=diagnose,
        )
        right_explore = run_explore(
            blend_file=right,
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
                    "meta": {
                        "left_file": str(left),
                        "right_file": str(right),
                        "scope": scope,
                    },
                    "summary": {},
                    "data": {"changes": {}},
                    "warnings": [],
                    "errors": [str(exc)],
                },
                ensure_ascii=True,
            )
        )
        raise typer.Exit(code=1) from exc

    probe_errors = list(left_explore.errors) + list(right_explore.errors)
    if probe_errors:
        typer.echo(
            json.dumps(
                {
                    "meta": {
                        "left_file": str(left),
                        "right_file": str(right),
                        "scope": scope,
                    },
                    "summary": {},
                    "data": {"changes": {}},
                    "warnings": [],
                    "errors": probe_errors,
                },
                ensure_ascii=True,
            )
        )
        raise typer.Exit(code=1)

    result = _build_compare_result(left_explore, right_explore)

    if pretty:
        render_compare_pretty(result)
    else:
        typer.echo(result.model_dump_json())

    if not result.meta.identical:
        raise typer.Exit(code=1)
