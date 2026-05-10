"""Helper utilities for the create command."""

from __future__ import annotations

from pathlib import Path

from gleb.core.blender_runner import run_blender_script
from gleb.models.create_schema import CreateResult


def run_create(
    output: Path,
    assets: list[str],
    blender_path: str | None = None,
    quiet: bool = False,
) -> CreateResult:
    probe_script = Path(__file__).resolve().parents[1] / "blender_scripts" / "create_probe.py"
    payload = {
        "assets": assets,
        "output_path": str(output.resolve()),
    }
    probe_result, blender_version = run_blender_script(
        probe_script, payload, blender_path=blender_path, quiet=quiet
    )

    merged = {
        "meta": {
            "output": str(output),
            "blender_version": blender_version,
            "command": "create",
        },
        "summary": probe_result.get("summary", {}),
        "data": probe_result.get("data", {}),
        "warnings": probe_result.get("warnings", []),
        "errors": probe_result.get("errors", []),
    }
    return CreateResult.model_validate(merged)
