"""Create a new .blend file with the pipeline-compatible collection hierarchy."""

from __future__ import annotations

import sys
from pathlib import Path

import bpy

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _shared import decode_payload_from_argv, dump_json_line  # noqa: E402


def _clear_default_scene() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    for light in list(bpy.data.lights):
        bpy.data.lights.remove(light)
    for cam in list(bpy.data.cameras):
        bpy.data.cameras.remove(cam)


def _new_collection(name: str, parent: bpy.types.Collection | None = None) -> bpy.types.Collection:
    coll = bpy.data.collections.new(name)
    if parent is not None:
        parent.children.link(coll)
    else:
        bpy.context.scene.collection.children.link(coll)
    return coll


def _build_hierarchy(asset_names: list[str]) -> tuple[list[str], list[str]]:
    """
    Create _support/ plus optional seed asset collections.
    Collection datablock names are global in Blender — each asset uses distinct
    visual_<asset>/mesh_<asset>/layer_<N>_<asset> and
    static_<asset>/trimesh_<asset>/tri_layer_<N>_<asset>.
    Returns (flat list of collection paths created, list of asset names).
    """
    scene_root = bpy.context.scene.collection

    for child in list(scene_root.children):
        scene_root.children.unlink(child)

    created: list[str] = []

    support = _new_collection("_support")
    created.append("_support")

    valid_assets: list[str] = []
    seen: set[str] = set()
    for raw in asset_names:
        name = str(raw).strip()
        if not name or name in seen:
            continue
        if name.startswith("_"):
            continue
        if bpy.data.collections.get(name) is not None:
            continue
        seen.add(name)
        valid_assets.append(name)

    for asset_name in valid_assets:
        asset = _new_collection(asset_name)
        created.append(asset_name)

        visual = _new_collection(f"visual_{asset_name}", asset)
        created.append(f"{asset_name}/visual_{asset_name}")
        mesh_c = _new_collection(f"mesh_{asset_name}", visual)
        created.append(f"{asset_name}/visual_{asset_name}/mesh_{asset_name}")
        _new_collection(f"layer_1_{asset_name}", mesh_c)
        created.append(f"{asset_name}/visual_{asset_name}/mesh_{asset_name}/layer_1_{asset_name}")

        static_c = _new_collection(f"static_{asset_name}", asset)
        created.append(f"{asset_name}/static_{asset_name}")
        tri_c = _new_collection(f"trimesh_{asset_name}", static_c)
        created.append(f"{asset_name}/static_{asset_name}/trimesh_{asset_name}")
        _new_collection(f"tri_layer_1_{asset_name}", tri_c)
        created.append(f"{asset_name}/static_{asset_name}/trimesh_{asset_name}/tri_layer_1_{asset_name}")

    return created, valid_assets


def main() -> None:
    payload = decode_payload_from_argv()
    output_path = str(payload.get("output_path", ""))
    assets_raw = payload.get("assets", [])
    if not isinstance(assets_raw, list):
        assets_raw = []
    asset_names = [str(a) for a in assets_raw]

    errors: list[str] = []
    warnings: list[str] = []

    if not output_path:
        dump_json_line(
            {
                "summary": {"collections_created": 0, "assets_created": 0},
                "data": {"assets": [], "collections": [], "output_path": ""},
                "warnings": warnings,
                "errors": ["Missing 'output_path' in payload."],
            }
        )
        return

    _clear_default_scene()
    created, valid_assets = _build_hierarchy(asset_names)

    try:
        bpy.ops.wm.save_as_mainfile(filepath=output_path)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"save: {exc}")

    dump_json_line(
        {
            "summary": {
                "collections_created": len(created),
                "assets_created": len(valid_assets),
            },
            "data": {
                "assets": valid_assets,
                "collections": created,
                "output_path": output_path,
            },
            "warnings": warnings,
            "errors": errors,
        }
    )


if __name__ == "__main__":
    main()
