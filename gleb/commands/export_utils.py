"""Helper utilities for the export command."""

from __future__ import annotations

from pathlib import Path

from gleb.core.blender_runner import run_blender_probe
from gleb.models.export_schema import ExportResult
from gleb.commands.sidecar import write_godot_import_sidecar


def run_export(
    blend_file: Path,
    output_dir: Path,
    assets: list[str] | None = None,
    apply_modifiers: bool = True,
    export_tangents: bool = True,
    export_materials: str = "EXPORT",
    bake_uv2: bool = False,
    uv2_method: str = "smart",
    uv2_margin: float = 0.02,
    target_texel_density: float = 4.0,
    lightmap_texel_density_prop: str = "lightmap_texel_density",
    write_import_sidecar: bool = False,
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
        "bake_uv2": bake_uv2,
        "uv2_method": uv2_method,
        "uv2_margin": uv2_margin,
        "target_texel_density": target_texel_density,
        "lightmap_texel_density_prop": lightmap_texel_density_prop,
    }
    probe_result, blender_version = run_blender_probe(
        blend_file, probe_script, payload, blender_path=blender_path, quiet=quiet
    )

    data = probe_result.get("data", {})
    warnings = list(probe_result.get("warnings", []))

    if write_import_sidecar:
        exports = data.get("exports", []) if isinstance(data, dict) else []
        for entry in exports:
            if not isinstance(entry, dict):
                continue
            if entry.get("status") != "exported":
                continue
            glb_path = entry.get("path")
            if not glb_path:
                continue
            texel_size = entry.get("lightmap_texel_size")
            if texel_size is None:
                texel_size = 1.0 / target_texel_density if target_texel_density > 0 else 0.25
            sidecar_path, was_written, msg = write_godot_import_sidecar(
                Path(glb_path), float(texel_size)
            )
            entry["sidecar_path"] = str(sidecar_path) if was_written else None
            if msg:
                warnings.append(msg)

    merged = {
        "meta": {
            "file": str(blend_file),
            "output_dir": str(output_dir),
            "blender_version": blender_version,
            "command": "export",
        },
        "summary": probe_result.get("summary", {}),
        "data": data,
        "warnings": warnings,
        "errors": probe_result.get("errors", []),
    }
    return ExportResult.model_validate(merged)
