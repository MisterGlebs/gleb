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


def _find_layer_collection(
    layer_coll: bpy.types.LayerCollection, target: bpy.types.Collection
) -> bpy.types.LayerCollection | None:
    if layer_coll.collection is target:
        return layer_coll
    for child in layer_coll.children:
        found = _find_layer_collection(child, target)
        if found is not None:
            return found
    return None


def main() -> None:
    payload = decode_payload_from_argv()
    blend_path = str(payload.get("blend_path", ""))
    assets = payload.get("assets", [])
    if not isinstance(assets, list):
        assets = []
    visual_prefix = str(payload.get("visual_object_prefix", "Vis"))
    support_name = str(payload.get("support_object_name", "SupportCube"))
    subsurf_levels = int(payload.get("subsurf_levels", 2))

    array_count = int(payload.get("array_count", 1) or 1)
    seed_collision = bool(payload.get("seed_collision", False))
    pre_existing_uv2 = bool(payload.get("pre_existing_uv2", False))
    asset_density_override_raw = payload.get("asset_density_override")
    asset_density_override = (
        float(asset_density_override_raw)
        if asset_density_override_raw is not None
        else None
    )
    exclude_asset_layer = bool(payload.get("exclude_asset_layer", False))
    custom_uv0_name_raw = payload.get("custom_uv0_name")
    custom_uv0_name = str(custom_uv0_name_raw) if custom_uv0_name_raw else None
    seed_parented_child = bool(payload.get("seed_parented_child", False))

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

        if array_count > 1:
            arr = obj.modifiers.new(name="Array", type="ARRAY")
            arr.count = array_count
            arr.use_relative_offset = True
            arr.relative_offset_displace = (1.5, 0.0, 0.0)
            arr.use_merge_vertices = False

        if pre_existing_uv2:
            mesh = obj.data
            if mesh is not None and len(mesh.uv_layers) < 2:
                mesh.uv_layers.new(name="Pre", do_init=True)

        if custom_uv0_name and obj.data is not None and len(obj.data.uv_layers) >= 1:
            obj.data.uv_layers[0].name = custom_uv0_name
            # Stamp a sentinel UV0 value so we can detect TEXCOORD_0 / TEXCOORD_1
            # ordering after a glTF round-trip (which strips UV layer names).
            uv0_data = obj.data.uv_layers[0].data
            for li in range(len(uv0_data)):
                uv0_data[li].uv = (0.42, 0.17)

        if asset_density_override is not None:
            asset_root = bpy.data.collections.get(asset)
            if asset_root is not None:
                asset_root["lightmap_texel_density"] = asset_density_override

        if seed_parented_child:
            # Add a second visual mesh inside the same layer collection that is
            # *parented* to the first. The Blender glTF exporter silently drops
            # selected objects whose parent is missing from the selection, so the
            # bake/swap pipeline must keep parent links intact across replacements.
            bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, location=(0.0, 2.0, 0.0))
            child = view_layer.objects.active
            if child is not None:
                child.name = f"{visual_prefix}_{asset}_child"
                _link_only_to(child, layer_coll)
                child.parent = obj
                child.matrix_parent_inverse = obj.matrix_world.inverted()
                created.append(child.name)

        if seed_collision:
            tri_coll_name = f"tri_layer_1_{asset}"
            tri_coll = bpy.data.collections.get(tri_coll_name)
            if tri_coll is not None:
                bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 5.0, 0.0))
                col_obj = view_layer.objects.active
                if col_obj is not None:
                    col_obj.name = f"Col_{asset}"
                    _link_only_to(col_obj, tri_coll)
                    created.append(col_obj.name)

        if exclude_asset_layer:
            asset_root = bpy.data.collections.get(asset)
            if asset_root is not None:
                lc = _find_layer_collection(view_layer.layer_collection, asset_root)
                if lc is not None:
                    lc.exclude = True

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
