"""Helper utilities for the edit command."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gleb.core.blender_runner import run_blender_probe
from gleb.models.edit_schema import EditResult


def run_edit(
    blend_file: Path,
    operations: list[dict[str, Any]],
    dry_run: bool,
    output: Path | None,
    blender_path: str | None = None,
    quiet: bool = False,
) -> EditResult:
    probe_script = Path(__file__).resolve().parents[1] / "blender_scripts" / "edit_probe.py"
    payload: dict[str, Any] = {
        "operations": operations,
        "dry_run": dry_run,
        "output_path": str(output) if output else None,
    }
    probe_result, blender_version = run_blender_probe(
        blend_file, probe_script, payload, blender_path=blender_path, quiet=quiet
    )

    merged = {
        "meta": {
            "file": str(blend_file),
            "blender_version": blender_version,
            "command": "edit",
            "dry_run": dry_run,
            "operations_count": len(operations),
        },
        "summary": probe_result.get("summary", {}),
        "data": probe_result.get("data", {}),
        "warnings": probe_result.get("warnings", []),
        "errors": probe_result.get("errors", []),
    }
    return EditResult.model_validate(merged)
