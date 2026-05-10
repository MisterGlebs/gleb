"""Populate a pipeline-style .blend with meshes for round-trip tests (runs inside Blender)."""

from __future__ import annotations

import sys
from pathlib import Path

import bpy

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _shared import decode_payload_from_argv, dump_json_line  # noqa: E402


def _link_only_to(obj: bpy.types.Object, coll: bpy.types.Collection) -> None:
    for uc in list(obj.users_collection):
        uc.objects.unlink(obj)
    coll.objects.link(obj)


def main() -> None:
    payload = decode_payload_from_argv()
    blend_path = str(payload.get("blend_path", ""))
    assets = payload.get("assets", [])
    if not isinstance(assets, list):
        assets = []
    visual_prefix = str(payload.get("visual_object_prefix", "Vis"))
    support_name = str(payload.get("support_object_name", "SupportCube"))
    subsurf_levels = int(payload.get("subsurf_levels", 2))

    errors: list[str] = []
    created: list[str] = []

    if not blend_path:
        dump_json_line({"summary": {}, "data": {}, "warnings": [], "errors": ["Missing blend_path"]})
        return

    try:
        bpy.ops.wm.open_mainfile(filepath=blend_path)
    except Exception as exc:  # noqa: BLE001
        dump_json_line({"summary": {}, "data": {}, "warnings": [], "errors": [f"open: {exc}"]})
        return

    view_layer = bpy.context.view_layer

    for asset in assets:
        asset = str(asset).strip()
        if not asset:
            continue
        layer_coll_name = f"layer_1_{asset}"
        layer_coll = bpy.data.collections.get(layer_coll_name)
        if layer_coll is None:
            errors.append(f"Collection '{layer_coll_name}' not found.")
            continue

        obj_name = f"{visual_prefix}_{asset}"
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.0))
        obj = view_layer.objects.active
        if obj is None:
            errors.append(f"Cube add failed for {asset}.")
            continue
        obj.name = obj_name
        _link_only_to(obj, layer_coll)

        mod = obj.modifiers.new(name="Subdivision", type="SUBSURF")
        mod.levels = subsurf_levels
        mod.render_levels = subsurf_levels

        created.append(obj_name)

    support_coll = bpy.data.collections.get("_support")
    if support_coll is not None:
        bpy.ops.mesh.primitive_cube_add(size=0.5, location=(100.0, 0.0, 0.0))
        sup = view_layer.objects.active
        if sup is not None:
            sup.name = support_name
            _link_only_to(sup, support_coll)
            created.append(support_name)

    try:
        bpy.ops.wm.save_mainfile(filepath=blend_path)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"save: {exc}")

    dump_json_line(
        {
            "summary": {"objects_created": len(created)},
            "data": {"objects": created},
            "warnings": [],
            "errors": errors,
        }
    )


if __name__ == "__main__":
    main()
