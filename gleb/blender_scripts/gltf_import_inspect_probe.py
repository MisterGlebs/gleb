"""Import .glb files in a fresh Blender session and report mesh object metadata (runs inside Blender)."""

from __future__ import annotations

import json
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


def _uv2_island_overlaps(mesh: bpy.types.Mesh) -> bool:
    """Detect whether the UV2 islands of disconnected vertex groups overlap.

    Used by tests to verify Array-modifier bakes produce unique islands per
    copy. Walks face -> connected-component partition (by shared vertices),
    computes UV2 bbox per component, returns True if any two bboxes intersect
    (with a small epsilon tolerance).
    """
    if len(mesh.uv_layers) < 2:
        return False
    uv_layer = mesh.uv_layers[1].data
    parent = list(range(len(mesh.vertices)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for poly in mesh.polygons:
        verts = list(poly.vertices)
        for i in range(1, len(verts)):
            union(verts[0], verts[i])

    bboxes: dict[int, list[float]] = {}
    for poly in mesh.polygons:
        root = find(poly.vertices[0])
        for li in poly.loop_indices:
            uv = uv_layer[li].uv
            bb = bboxes.get(root)
            if bb is None:
                bboxes[root] = [uv.x, uv.y, uv.x, uv.y]
            else:
                if uv.x < bb[0]:
                    bb[0] = uv.x
                if uv.y < bb[1]:
                    bb[1] = uv.y
                if uv.x > bb[2]:
                    bb[2] = uv.x
                if uv.y > bb[3]:
                    bb[3] = uv.y

    eps = 1e-5
    keys = list(bboxes.keys())
    for i in range(len(keys)):
        a = bboxes[keys[i]]
        for j in range(i + 1, len(keys)):
            b = bboxes[keys[j]]
            if a[2] < b[0] + eps or b[2] < a[0] + eps:
                continue
            if a[3] < b[1] + eps or b[3] < a[1] + eps:
                continue
            return True
    return False


def _object_payload(o: bpy.types.Object) -> dict[str, Any]:
    mesh = o.data if o.type == "MESH" else None
    nv = len(mesh.vertices) if mesh is not None else 0
    extras: dict[str, Any] = {}
    for k in o.keys():
        try:
            value = o[k]
        except Exception:  # noqa: BLE001
            extras[k] = None
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            extras[k] = value
        elif hasattr(value, "to_list"):
            try:
                extras[k] = value.to_list()
            except Exception:  # noqa: BLE001
                extras[k] = repr(value)
        else:
            try:
                json.dumps(value)
                extras[k] = value
            except (TypeError, ValueError):
                try:
                    extras[k] = list(value)
                except Exception:  # noqa: BLE001
                    extras[k] = repr(value)
    if mesh is not None:
        uv_layer_names = [layer.name for layer in mesh.uv_layers]
        uv_layers_count = len(uv_layer_names)
        uv2_overlaps = _uv2_island_overlaps(mesh) if uv_layers_count >= 2 else False
        uv0_sample = (
            [mesh.uv_layers[0].data[0].uv.x, mesh.uv_layers[0].data[0].uv.y]
            if uv_layers_count >= 1 and len(mesh.uv_layers[0].data) > 0
            else None
        )
    else:
        uv_layer_names = []
        uv_layers_count = 0
        uv2_overlaps = False
        uv0_sample = None
    return {
        "name": o.name,
        "type": o.type,
        "vertices": nv,
        "extras": extras,
        "uv_layers": uv_layers_count,
        "uv_layer_names": uv_layer_names,
        "uv2_island_overlaps": uv2_overlaps,
        "uv0_sample": uv0_sample,
    }


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
