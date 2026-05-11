"""Godot import sidecar writers for `gleb export`."""

from __future__ import annotations

from pathlib import Path


def _format_godot_import(texel_size: float) -> str:
    """Render a minimal Godot 4.x scene-import config for a baked-UV2 .glb.

    Sets `meshes/light_baking = 2` (Static Lightmaps) and the per-import
    `meshes/lightmap_texel_size`. UV2 is shipped inside the .glb (TEXCOORD_1),
    so Godot's xatlas fallback never runs.
    """
    return (
        "[remap]\n"
        '\nimporter="scene"\n'
        'type="PackedScene"\n'
        "\n"
        "[params]\n"
        "\n"
        "meshes/light_baking=2\n"
        f"meshes/lightmap_texel_size={texel_size:.6f}\n"
        "meshes/generate_lods=true\n"
        "meshes/create_shadow_meshes=true\n"
        "nodes/use_node_type_suffixes=false\n"
    )


def write_godot_import_sidecar(
    glb_path: Path, texel_size: float
) -> tuple[Path, bool, str | None]:
    """Write `<glb_path>.import` if it does not already exist.

    Returns (sidecar_path, was_written, message). Never overwrites; if the
    sidecar exists, returns (path, False, "...preserved...") so the caller
    can surface it as a warning.
    """
    sidecar = Path(str(glb_path) + ".import")
    if sidecar.exists():
        return sidecar, False, (
            f"sidecar preserved: {sidecar} already exists; "
            "delete it (or use --force-import-sidecar in v2) to refresh."
        )

    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(_format_godot_import(texel_size), encoding="utf-8")
    return sidecar, True, None
