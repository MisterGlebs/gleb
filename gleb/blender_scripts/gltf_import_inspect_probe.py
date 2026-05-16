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
    """Detect whether distinct UV2 islands have overlapping AABBs.

    A UV island is a set of polygons connected by **shared UV vertices**: two
    polygons are in the same island iff some 3D vertex belongs to both AND
    they store the same UV coords for that vertex (no UV seam between them).
    This matches Blender's UV editor definition of an island.

    We deliberately do NOT use 3D vertex topology — glTF round-trips split
    vertices at every UV seam, so 3D topology partitions every face into its
    own component and the bbox check becomes meaningless.

    Returns True iff any two distinct islands' UV2 AABBs intersect.
    """
    if len(mesh.uv_layers) < 2 or len(mesh.polygons) == 0:
        return False
    uv_layer = mesh.uv_layers[1].data
    n_polys = len(mesh.polygons)
    parent = list(range(n_polys))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Bucket polys by (quantized 3D position, quantized UV) and union polys
    # that share any such key. We use 3D POSITION (not vertex index) because
    # glTF round-trips split vertices at every UV seam — two split copies of
    # the same 3D point have different vertex indices but identical positions,
    # and matching UVs at a shared 3D point still mean "no seam between us".
    uv_quant = 1.0 / 1e-5
    pos_quant = 1.0 / 1e-5
    verts = mesh.vertices
    bucket: dict[tuple[int, int, int, int, int], int] = {}
    for pi, poly in enumerate(mesh.polygons):
        for li, vi in zip(poly.loop_indices, poly.vertices):
            uv = uv_layer[li].uv
            co = verts[vi].co
            key = (
                int(round(co.x * pos_quant)),
                int(round(co.y * pos_quant)),
                int(round(co.z * pos_quant)),
                int(round(uv.x * uv_quant)),
                int(round(uv.y * uv_quant)),
            )
            other = bucket.get(key)
            if other is None:
                bucket[key] = pi
            else:
                union(pi, other)

    bboxes: dict[int, list[float]] = {}
    for pi, poly in enumerate(mesh.polygons):
        root = find(pi)
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

    eps = 1e-4
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


def _principled_node(mat: bpy.types.Material) -> bpy.types.ShaderNode | None:
    if not mat.use_nodes or mat.node_tree is None:
        return None
    for n in mat.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            return n
    return None


def _material_payload(mat: bpy.types.Material | None) -> dict[str, Any] | None:
    if mat is None:
        return None
    pr = _principled_node(mat)
    base_color: list[float] | None = None
    base_color_linked: str | None = None
    alpha_default: float | None = None
    alpha_linked: str | None = None
    if pr is not None:
        b = pr.inputs.get("Base Color")
        if b is not None:
            if b.is_linked:
                base_color_linked = b.links[0].from_node.type
            else:
                base_color = list(b.default_value)
        a = pr.inputs.get("Alpha")
        if a is not None:
            if a.is_linked:
                alpha_linked = a.links[0].from_node.type
            else:
                alpha_default = float(a.default_value)
    return {
        "name": mat.name,
        "use_nodes": bool(mat.use_nodes),
        "blend_method": getattr(mat, "blend_method", None)
        or getattr(getattr(mat, "surface_render_method", None), "name", None),
        "use_backface_culling": bool(mat.use_backface_culling),
        "diffuse_color": list(mat.diffuse_color),
        "metallic": float(mat.metallic),
        "roughness": float(mat.roughness),
        "principled_present": pr is not None,
        "base_color_default": base_color,
        "base_color_linked_from": base_color_linked,
        "alpha_default": alpha_default,
        "alpha_linked_from": alpha_linked,
    }


def _slot_payload(slot: bpy.types.MaterialSlot) -> dict[str, Any]:
    return {
        "link": slot.link,
        "material": _material_payload(slot.material),
    }


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
        polys = len(mesh.polygons)
        polys_per_slot: dict[str, int] = {}
        for poly in mesh.polygons:
            key = str(poly.material_index)
            polys_per_slot[key] = polys_per_slot.get(key, 0) + 1
    else:
        uv_layer_names = []
        uv_layers_count = 0
        uv2_overlaps = False
        uv0_sample = None
        polys = 0
        polys_per_slot = {}
    material_slots = [_slot_payload(s) for s in o.material_slots] if o.type == "MESH" else []
    return {
        "name": o.name,
        "type": o.type,
        "parent": o.parent.name if o.parent is not None else None,
        "vertices": nv,
        "polygons": polys,
        "extras": extras,
        "uv_layers": uv_layers_count,
        "uv_layer_names": uv_layer_names,
        "uv2_island_overlaps": uv2_overlaps,
        "uv0_sample": uv0_sample,
        "material_slots": material_slots,
        "polys_per_slot": polys_per_slot,
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
