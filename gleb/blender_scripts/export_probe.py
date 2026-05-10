"""Export pipeline assets from a .blend file as .glb files (one per root asset collection)."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

import bpy

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _shared import decode_payload_from_argv, dump_json_line  # noqa: E402

# --- Visual: layer_<N>_<assetSlug> under mesh_* / multimesh_* ------------------
_LAYER_WITH_ASSET_RE = re.compile(r"^layer_(\d+)_(.+)$")
_LAYER_RE = re.compile(r"^layer_(\d+)(?:\.\d+)?$")

# --- Static trimesh bucket: tri_layer_<N>_<asset> -----------------------------
_TRI_LAYER_WITH_ASSET_RE = re.compile(r"^tri_layer_(\d+)_(.+)$")
_TRI_LAYER_RE = re.compile(r"^tri_layer_(\d+)(?:\.\d+)?$")

# --- Static convex bucket: cvx_layer_<N>_<asset> ------------------------------
_CVX_LAYER_WITH_ASSET_RE = re.compile(r"^cvx_layer_(\d+)_(.+)$")
_CVX_LAYER_RE = re.compile(r"^cvx_layer_(\d+)(?:\.\d+)?$")

# --- Static box bucket: box_layer_<N>_<asset> ---------------------------------
_BOX_LAYER_WITH_ASSET_RE = re.compile(r"^box_layer_(\d+)_(.+)$")
_BOX_LAYER_RE = re.compile(r"^box_layer_(\d+)(?:\.\d+)?$")


def _parse_visual_layer_index(layer_coll_name: str) -> int | None:
    m = _LAYER_WITH_ASSET_RE.match(layer_coll_name)
    if m:
        return int(m.group(1))
    m = _LAYER_RE.match(layer_coll_name)
    if m:
        return int(m.group(1))
    return None


def _parse_tri_layer_index(name: str) -> int | None:
    m = _TRI_LAYER_WITH_ASSET_RE.match(name)
    if m:
        return int(m.group(1))
    m = _TRI_LAYER_RE.match(name)
    if m:
        return int(m.group(1))
    return None


def _parse_cvx_layer_index(name: str) -> int | None:
    m = _CVX_LAYER_WITH_ASSET_RE.match(name)
    if m:
        return int(m.group(1))
    m = _CVX_LAYER_RE.match(name)
    if m:
        return int(m.group(1))
    return None


def _parse_box_layer_index(name: str) -> int | None:
    m = _BOX_LAYER_WITH_ASSET_RE.match(name)
    if m:
        return int(m.group(1))
    m = _BOX_LAYER_RE.match(name)
    if m:
        return int(m.group(1))
    return None


def _parse_static_layer_index(layer_coll_name: str, collision_kind: str) -> int | None:
    if collision_kind == "collision_trimesh":
        return _parse_tri_layer_index(layer_coll_name)
    if collision_kind == "collision_convex":
        return _parse_cvx_layer_index(layer_coll_name)
    if collision_kind == "collision_box":
        return _parse_box_layer_index(layer_coll_name)
    return None


def _find_visual_roots(asset_coll: bpy.types.Collection) -> list[bpy.types.Collection]:
    """Collections whose name starts with 'visual' under the asset root."""
    return [c for c in asset_coll.children if c.name.startswith("visual")]


def _find_static_roots(asset_coll: bpy.types.Collection) -> list[bpy.types.Collection]:
    """Collections whose name starts with 'static' under the asset root."""
    return [c for c in asset_coll.children if c.name.startswith("static")]


def _godot_type_for_shape_bucket(bucket_coll: bpy.types.Collection) -> str | None:
    """Map static_* child (trimesh_*, convex_*, box_*) to godot_type."""
    n = bucket_coll.name
    if n.startswith("trimesh"):
        return "collision_trimesh"
    if n.startswith("convex"):
        return "collision_convex"
    if n.startswith("box"):
        return "collision_box"
    return None


def _stamp_visual_collision_defaults(asset_coll: bpy.types.Collection, warnings: list[str]) -> None:
    """
    Apply godot_type / render_layers / collision extras based on collection membership.
    Per-object keys already set are never overwritten.

    Structure:
      visual_*/mesh_*/layer_<N>_*/
      visual_*/multimesh_*/layer_<N>_*/   (same stamping as mesh for now)
      static_*/trimesh_*/tri_layer_<N>_*/
      static_*/convex_*/cvx_layer_<N>_*/
      static_*/box_*/box_layer_<N>_*/
    """
    stamped_objects: set[bpy.types.Object] = set()

    for visual_root in _find_visual_roots(asset_coll):
        for render_root in visual_root.children:
            if not (
                render_root.name.startswith("mesh")
                or render_root.name.startswith("multimesh")
            ):
                warnings.append(
                    f"[{asset_coll.name}] {visual_root.name}/{render_root.name}: "
                    f"expected child starting with 'mesh' or 'multimesh' — skipping."
                )
                continue
            for layer_coll in render_root.children:
                idx = _parse_visual_layer_index(layer_coll.name)
                if idx is None:
                    warnings.append(
                        f"[{asset_coll.name}] {visual_root.name}/{render_root.name}/"
                        f"{layer_coll.name}: name must match layer_<N>_<asset> or legacy "
                        f"layer_<N> — skipping layer collection."
                    )
                    continue
                bitmask = 1 << (idx - 1) if idx >= 1 else 1
                for obj in layer_coll.all_objects:
                    stamped_objects.add(obj)
                    if "godot_type" not in obj:
                        obj["godot_type"] = "mesh"
                    if "render_layers" not in obj:
                        obj["render_layers"] = bitmask

    for static_root in _find_static_roots(asset_coll):
        for shape_bucket in static_root.children:
            collision_kind = _godot_type_for_shape_bucket(shape_bucket)
            if collision_kind is None:
                warnings.append(
                    f"[{asset_coll.name}] {static_root.name}/{shape_bucket.name}: "
                    f"expected child starting with 'trimesh', 'convex', or 'box' — skipping."
                )
                continue
            for layer_coll in shape_bucket.children:
                idx = _parse_static_layer_index(layer_coll.name, collision_kind)
                if idx is None:
                    exp = (
                        "tri_layer_<N>_<asset> or tri_layer_<N>"
                        if collision_kind == "collision_trimesh"
                        else (
                            "cvx_layer_<N>_<asset> or cvx_layer_<N>"
                            if collision_kind == "collision_convex"
                            else "box_layer_<N>_<asset> or box_layer_<N>"
                        )
                    )
                    warnings.append(
                        f"[{asset_coll.name}] {static_root.name}/{shape_bucket.name}/"
                        f"{layer_coll.name}: name must match {exp} — skipping."
                    )
                    continue
                layer_bit = 1 << (idx - 1) if idx >= 1 else 1
                for obj in layer_coll.all_objects:
                    stamped_objects.add(obj)
                    if "godot_type" not in obj:
                        obj["godot_type"] = collision_kind
                    if "collision_layer" not in obj:
                        obj["collision_layer"] = layer_bit
                    if "collision_mask" not in obj:
                        obj["collision_mask"] = 0

    for obj in asset_coll.objects:
        if obj not in stamped_objects:
            warnings.append(
                f"Object '{obj.name}' is placed directly under '{asset_coll.name}/' "
                f"(not under visual_*/mesh_*/layer_* or static_*/*/tri_layer_*|cvx_layer_*|box_layer_*) "
                f"— ignored by pipeline defaults."
            )


def _find_layer_collection(
    layer_coll: bpy.types.LayerCollection, target: bpy.types.Collection
) -> bpy.types.LayerCollection | None:
    """Recursively find the LayerCollection wrapping *target* under *layer_coll*."""
    if layer_coll.collection is target:
        return layer_coll
    for child in layer_coll.children:
        found = _find_layer_collection(child, target)
        if found is not None:
            return found
    return None


def _unexclude_recursively(
    layer_coll: bpy.types.LayerCollection, saved: list[tuple[bpy.types.LayerCollection, bool, bool]]
) -> None:
    """Un-exclude / un-hide a LayerCollection subtree, remembering prior state for restore."""
    saved.append((layer_coll, layer_coll.exclude, layer_coll.hide_viewport))
    layer_coll.exclude = False
    layer_coll.hide_viewport = False
    for child in layer_coll.children:
        _unexclude_recursively(child, saved)


def _export_collection_as_glb(
    asset_coll: bpy.types.Collection,
    output_path: str,
    warnings: list[str],
    *,
    apply_modifiers: bool = True,
    export_tangents: bool = True,
    export_materials: str = "EXPORT",
) -> bool:
    """Select all objects in *asset_coll* (recursively) and export as GLB."""
    all_objs = list(asset_coll.all_objects)
    if not all_objs:
        warnings.append(f"Asset '{asset_coll.name}' has no objects — skipping export.")
        return False

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    view_layer = bpy.context.view_layer
    asset_layer_coll = _find_layer_collection(view_layer.layer_collection, asset_coll)
    saved_layer_state: list[tuple[bpy.types.LayerCollection, bool, bool]] = []
    if asset_layer_coll is not None:
        _unexclude_recursively(asset_layer_coll, saved_layer_state)
        view_layer.update()
    else:
        warnings.append(
            f"Asset '{asset_coll.name}': no matching LayerCollection in active ViewLayer."
        )

    for obj in bpy.data.objects:
        obj.select_set(False)

    hide_states: dict[str, tuple[bool, bool]] = {}
    selected: list[bpy.types.Object] = []
    skipped_not_in_view_layer: list[str] = []
    for obj in all_objs:
        hide_states[obj.name] = (obj.hide_viewport, obj.hide_render)
        obj.hide_viewport = False
        try:
            obj.select_set(True)
        except RuntimeError:
            skipped_not_in_view_layer.append(obj.name)
            continue
        selected.append(obj)

    if skipped_not_in_view_layer:
        sample = ", ".join(skipped_not_in_view_layer[:5])
        more = "" if len(skipped_not_in_view_layer) <= 5 else f" (+{len(skipped_not_in_view_layer) - 5} more)"
        warnings.append(
            f"Asset '{asset_coll.name}': skipped {len(skipped_not_in_view_layer)} object(s) "
            f"not in active ViewLayer (collection excluded?): {sample}{more}"
        )

    if not selected:
        warnings.append(
            f"Asset '{asset_coll.name}' has no selectable objects in active ViewLayer — skipping export."
        )
        return False

    bpy.context.view_layer.objects.active = selected[0]

    try:
        bpy.ops.export_scene.gltf(
            filepath=output_path,
            export_format="GLB",
            use_selection=True,
            export_extras=True,
            export_yup=True,
            export_materials=export_materials,
            export_apply=apply_modifiers,
            export_tangents=export_tangents,
            export_texcoords=True,
            export_normals=True,
            export_animations=True,
        )
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"glTF export failed for '{asset_coll.name}': {exc}")
        return False
    finally:
        for obj in all_objs:
            if obj.name in hide_states:
                obj.hide_viewport, obj.hide_render = hide_states[obj.name]
        for lc, exclude, hide_vp in saved_layer_state:
            try:
                lc.exclude = exclude
                lc.hide_viewport = hide_vp
            except Exception:  # noqa: BLE001
                pass

    return True


def main() -> None:
    payload = decode_payload_from_argv()
    output_dir: str = str(payload.get("output_dir", ""))
    apply_modifiers = payload.get("apply_modifiers", True)
    if not isinstance(apply_modifiers, bool):
        apply_modifiers = bool(apply_modifiers)
    export_tangents = payload.get("export_tangents", True)
    if not isinstance(export_tangents, bool):
        export_tangents = bool(export_tangents)
    materials_raw = payload.get("export_materials", "EXPORT")
    export_materials = str(materials_raw) if materials_raw else "EXPORT"
    if export_materials not in {"EXPORT", "PLACEHOLDER", "VIEWPORT", "NONE"}:
        export_materials = "EXPORT"

    filter_raw = payload.get("assets", []) or []
    if not isinstance(filter_raw, list):
        filter_raw = []
    asset_filter = {str(a).strip() for a in filter_raw if str(a).strip()}

    errors: list[str] = []
    warnings: list[str] = []
    exported: list[dict[str, Any]] = []

    if not output_dir:
        dump_json_line({
            "summary": {"assets_exported": 0, "assets_skipped": 0, "assets_failed": 0},
            "data": {"exports": [], "output_dir": ""},
            "warnings": warnings,
            "errors": ["Missing 'output_dir' in payload."],
        })
        return

    scene_root = bpy.context.scene.collection
    asset_collections = [
        c for c in scene_root.children
        if not c.name.startswith("_")
    ]

    if not asset_collections:
        dump_json_line({
            "summary": {"assets_exported": 0, "assets_skipped": 0, "assets_failed": 0},
            "data": {"exports": [], "output_dir": output_dir},
            "warnings": warnings,
            "errors": [
                "No exportable asset collections: add a root collection (name must not start with '_')."
            ],
        })
        return

    n_exported = n_skipped = n_failed = 0

    for asset_coll in asset_collections:
        name = asset_coll.name
        if asset_filter and name not in asset_filter:
            n_skipped += 1
            continue

        _stamp_visual_collision_defaults(asset_coll, warnings)

        glb_path = os.path.join(output_dir, f"{name}.glb")
        success = _export_collection_as_glb(
            asset_coll,
            glb_path,
            warnings,
            apply_modifiers=apply_modifiers,
            export_tangents=export_tangents,
            export_materials=export_materials,
        )
        if success:
            n_exported += 1
            exported.append({"asset": name, "path": glb_path, "status": "exported"})
        else:
            n_failed += 1
            exported.append({"asset": name, "path": glb_path, "status": "failed"})

    dump_json_line({
        "summary": {
            "assets_exported": n_exported,
            "assets_skipped": n_skipped,
            "assets_failed": n_failed,
        },
        "data": {
            "output_dir": output_dir,
            "exports": exported,
        },
        "warnings": warnings,
        "errors": errors,
    })


if __name__ == "__main__":
    main()
