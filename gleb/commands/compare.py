"""CLI command: compare two .blend files via explore snapshots."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from gleb.commands.explore_utils import normalize_match, normalize_scope, run_explore
from gleb.core.exceptions import GlebError
from gleb.core.json_diff import diff_any, flatten_diff_paths
from gleb.formatters.pretty import render_compare_pretty
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
    left_blend: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        help="Baseline .blend file (opened read-only).",
    ),
    right_blend: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        help="Comparison .blend file (opened read-only).",
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
    """Compare two .blend files using the same explore probe on each side.

    Exit code 0 only when structured summary and data sections match; otherwise 1
    (including probe failures). Left/right map to baseline vs candidate ordering.
    """
    names = object_names or []
    try:
        normalized_scope = normalize_scope(scope)
        normalized_match = normalize_match(match)
        left = run_explore(
            blend_file=left_blend,
            scope=normalized_scope,
            object_names=names,
            match=normalized_match,
            ignore_case=ignore_case,
            detail=detail,
            diagnose=diagnose,
        )
        right = run_explore(
            blend_file=right_blend,
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
                        "left_file": str(left_blend),
                        "right_file": str(right_blend),
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

    probe_errors = list(left.errors) + list(right.errors)
    if probe_errors:
        typer.echo(
            json.dumps(
                {
                    "meta": {
                        "left_file": str(left_blend),
                        "right_file": str(right_blend),
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

    result = _build_compare_result(left, right)

    if pretty:
        render_compare_pretty(result)
    else:
        typer.echo(result.model_dump_json())

    if not result.meta.identical:
        raise typer.Exit(code=1)
