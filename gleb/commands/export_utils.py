"""Helper utilities for the export command."""

from __future__ import annotations

from pathlib import Path

from gleb.core.blender_runner import run_blender_probe
from gleb.models.export_schema import ExportResult


def run_export(
    blend_file: Path,
    output_dir: Path,
    assets: list[str] | None = None,
    apply_modifiers: bool = True,
    export_tangents: bool = True,
    export_materials: str = "EXPORT",
    blender_path: str | None = None,
    quiet: bool = False,
) -> ExportResult:
    probe_script = Path(__file__).resolve().parents[1] / "blender_scripts" / "export_probe.py"
    payload = {
        "output_dir": str(output_dir.resolve()),
        "assets": assets or [],
        "apply_modifiers": apply_modifiers,
        "export_tangents": export_tangents,
        "export_materials": export_materials,
    }
    probe_result, blender_version = run_blender_probe(
        blend_file, probe_script, payload, blender_path=blender_path, quiet=quiet
    )

    data = probe_result.get("data", {})
    merged = {
        "meta": {
            "file": str(blend_file),
            "output_dir": str(output_dir),
            "blender_version": blender_version,
            "command": "export",
        },
        "summary": probe_result.get("summary", {}),
        "data": data,
        "warnings": probe_result.get("warnings", []),
        "errors": probe_result.get("errors", []),
    }
    return ExportResult.model_validate(merged)
