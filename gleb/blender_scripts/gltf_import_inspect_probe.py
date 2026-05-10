"""Import .glb files in a fresh Blender session and report mesh object metadata (runs inside Blender)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import bpy

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _shared import decode_payload_from_argv, dump_json_line  # noqa: E402


def _clear_scene_objects() -> None:
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def _object_payload(o: bpy.types.Object) -> dict[str, Any]:
    mesh = o.data if o.type == "MESH" else None
    nv = len(mesh.vertices) if mesh is not None else 0
    extras: dict[str, Any] = {}
    for k in o.keys():
        try:
            extras[k] = o[k]
        except Exception:  # noqa: BLE001
            extras[k] = None
    return {"name": o.name, "type": o.type, "vertices": nv, "extras": extras}


def main() -> None:
    payload = decode_payload_from_argv()
    paths_raw = payload.get("glb_paths", [])
    if not isinstance(paths_raw, list):
        paths_raw = []

    errors: list[str] = []
    imports_out: list[dict[str, Any]] = []

    _clear_scene_objects()

    for raw in paths_raw:
        path = str(raw).strip()
        if not path:
            continue
        try:
            bpy.ops.import_scene.gltf(filepath=path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"import {path}: {exc}")
            imports_out.append({"path": path, "objects": [], "import_failed": True})
            continue

        objs = [_object_payload(o) for o in bpy.context.scene.objects]
        imports_out.append({"path": path, "objects": objs, "import_failed": False})
        _clear_scene_objects()

    dump_json_line(
        {
            "summary": {"files_imported": len(imports_out)},
            "data": {"imports": imports_out},
            "warnings": [],
            "errors": errors,
        }
    )


if __name__ == "__main__":
    main()
