"""Helper utilities for the explore command."""

from __future__ import annotations

from pathlib import Path

from gleb.core.blender_runner import run_blender_probe
from gleb.models.explore_schema import ExploreResult, MatchMode, Scope

VALID_SCOPES = {
    "all",
    "scene",
    "collections",
    "objects",
    "materials",
    "modifiers",
    "animations",
    "relations",
    "constraints",
    "geometry",
    "textures",
    "armatures",
    "libraries",
    "custom_properties",
}
VALID_MATCHES = {"exact", "contains", "regex"}


def normalize_scope(scope: str) -> Scope:
    if scope not in VALID_SCOPES:
        raise ValueError(f"Invalid scope '{scope}'. Valid scopes: {', '.join(sorted(VALID_SCOPES))}")
    return scope  # type: ignore[return-value]


def normalize_match(match: str) -> MatchMode:
    if match not in VALID_MATCHES:
        raise ValueError(f"Invalid match '{match}'. Valid matches: {', '.join(sorted(VALID_MATCHES))}")
    return match  # type: ignore[return-value]


def run_explore(
    blend_file: Path,
    scope: Scope,
    object_names: list[str],
    match: MatchMode,
    ignore_case: bool,
    detail: bool,
    diagnose: bool,
) -> ExploreResult:
    probe_script = Path(__file__).resolve().parents[1] / "blender_scripts" / "explore_probe.py"
    payload = {
        "scope": scope,
        "detail": detail,
        "diagnose": diagnose,
        "query": {
            "object_names": object_names,
            "match": match,
            "ignore_case": ignore_case,
        },
    }
    probe_result, blender_version = run_blender_probe(blend_file, probe_script, payload)

    merged = {
        "meta": {
            "file": str(blend_file),
            "blender_version": blender_version,
            "scope": scope,
            "query": payload["query"],
        },
        "summary": probe_result.get("summary", {}),
        "data": probe_result.get("data", {}),
        "warnings": probe_result.get("warnings", []),
        "errors": probe_result.get("errors", []),
    }
    return ExploreResult.model_validate(merged)
