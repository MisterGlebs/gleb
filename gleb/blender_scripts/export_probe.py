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


# --- UV2 baking helpers --------------------------------------------------------


def _iter_visual_mesh_objects(asset_coll: bpy.types.Collection) -> list[bpy.types.Object]:
    """Return MESH objects under visual_*/(mesh|multimesh)_*/layer_*/ for the asset."""
    out: list[bpy.types.Object] = []
    seen: set[str] = set()
    for visual_root in _find_visual_roots(asset_coll):
        for render_root in visual_root.children:
            if not (
                render_root.name.startswith("mesh")
                or render_root.name.startswith("multimesh")
            ):
                continue
            for layer_coll in render_root.children:
                if _parse_visual_layer_index(layer_coll.name) is None:
                    continue
                for obj in layer_coll.all_objects:
                    if obj.type == "MESH" and obj.name not in seen:
                        seen.add(obj.name)
                        out.append(obj)
    return out


def _find_owning_collection(
    obj: bpy.types.Object, asset_coll: bpy.types.Collection
) -> bpy.types.Collection | None:
    """Return the descendant of asset_coll that directly contains *obj* (first hit)."""
    stack: list[bpy.types.Collection] = [asset_coll]
    while stack:
        coll = stack.pop()
        if obj.name in coll.objects:
            return coll
        stack.extend(coll.children)
    return None


def _bake_evaluated_copy(
    obj: bpy.types.Object,
    depsgraph: bpy.types.Depsgraph,
    target_collection: bpy.types.Collection,
) -> tuple[bpy.types.Object, bpy.types.Mesh]:
    """Create a duplicate of *obj* whose mesh data has all modifiers applied.

    Swaps the duplicate into *target_collection* and unlinks the original from it.
    Returns (new_obj, new_mesh). Caller must restore via _restore_swap.
    """
    eval_obj = obj.evaluated_get(depsgraph)
    me_eval = bpy.data.meshes.new_from_object(
        eval_obj, preserve_all_data_layers=True, depsgraph=depsgraph
    )
    me_eval.name = f"{obj.data.name}__uv2bake"

    new_obj = obj.copy()
    new_obj.data = me_eval
    new_obj.name = f"{obj.name}__uv2bake"
    for mod in list(new_obj.modifiers):
        new_obj.modifiers.remove(mod)

    target_collection.objects.link(new_obj)
    target_collection.objects.unlink(obj)
    return new_obj, me_eval


def _grid_pack_components(me: bpy.types.Mesh, margin: float) -> None:
    """Lay out per-connected-component UV2 islands into a grid in [0,1] UV space.

    Required after smart_project / unwrap on Array-style meshes because Blender's
    unwrap operators deduplicate identical-geometry components and stack their UV
    islands on top of each other. This pass walks vertex-connected components and
    assigns each one a distinct grid cell so lightmap atlases get unique texels per
    Array copy.
    """
    if len(me.uv_layers) < 2 or len(me.polygons) == 0:
        return
    uv_layer = me.uv_layers[1].data

    parent = list(range(len(me.vertices)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for poly in me.polygons:
        vs = list(poly.vertices)
        for i in range(1, len(vs)):
            union(vs[0], vs[i])

    comps: dict[int, list[int]] = {}
    for pi, poly in enumerate(me.polygons):
        comps.setdefault(find(poly.vertices[0]), []).append(pi)

    n = len(comps)
    if n <= 1:
        return

    import math

    cols = max(1, math.ceil(math.sqrt(n)))
    rows = max(1, math.ceil(n / cols))
    cell_w = 1.0 / cols
    cell_h = 1.0 / rows
    pad = min(margin, 0.45 * min(cell_w, cell_h))

    for idx, (_root, poly_idxs) in enumerate(sorted(comps.items())):
        row = idx // cols
        col = idx % cols
        bb_min_u = float("inf")
        bb_min_v = float("inf")
        bb_max_u = float("-inf")
        bb_max_v = float("-inf")
        for pi in poly_idxs:
            poly = me.polygons[pi]
            for li in poly.loop_indices:
                u, v = uv_layer[li].uv.x, uv_layer[li].uv.y
                if u < bb_min_u:
                    bb_min_u = u
                if v < bb_min_v:
                    bb_min_v = v
                if u > bb_max_u:
                    bb_max_u = u
                if v > bb_max_v:
                    bb_max_v = v
        bb_w = max(bb_max_u - bb_min_u, 1e-6)
        bb_h = max(bb_max_v - bb_min_v, 1e-6)
        target_w = cell_w - 2 * pad
        target_h = cell_h - 2 * pad
        scale = min(target_w / bb_w, target_h / bb_h)
        off_u = col * cell_w + pad
        off_v = row * cell_h + pad
        for pi in poly_idxs:
            poly = me.polygons[pi]
            for li in poly.loop_indices:
                u, v = uv_layer[li].uv.x, uv_layer[li].uv.y
                uv_layer[li].uv = (
                    (u - bb_min_u) * scale + off_u,
                    (v - bb_min_v) * scale + off_v,
                )


def _ensure_uv2(
    obj: bpy.types.Object,
    method: str,
    margin: float,
    warnings: list[str],
    asset_name: str,
) -> bool:
    """Add and unwrap a UV2 layer on *obj* in place. Return True if a layer was baked."""
    me = obj.data
    if me is None or len(me.polygons) == 0:
        return False
    if len(me.uv_layers) >= 2:
        return False

    if len(me.uv_layers) == 0:
        me.uv_layers.new(name="UVMap", do_init=True)

    uv0_name = me.uv_layers[0].name
    new_uv = me.uv_layers.new(name="UV2", do_init=False)
    if new_uv is None:
        warnings.append(f"[{asset_name}] {obj.name}: failed to create UV2 layer.")
        return False
    new_uv.active = True

    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.remove_doubles(threshold=1e-5)
        bpy.ops.mesh.normals_make_consistent(inside=False)
        if method == "lightmap_pack":
            bpy.ops.uv.lightmap_pack(
                PREF_CONTEXT="ALL_FACES",
                PREF_PACK_IN_ONE=True,
                PREF_NEW_UVLAYER=False,
                PREF_BOX_DIV=12,
                PREF_MARGIN_DIV=max(margin, 0.001) * 100.0,
            )
        else:
            bpy.ops.uv.smart_project(
                angle_limit=1.15,
                island_margin=margin,
                area_weight=0.0,
                correct_aspect=True,
                scale_to_bounds=False,
            )
        bpy.ops.uv.average_islands_scale()
        bpy.ops.uv.pack_islands(margin=margin)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"[{asset_name}] {obj.name}: UV2 unwrap failed: {exc}")
        return False
    finally:
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:  # noqa: BLE001
            pass

    # Blender's unwrap operators deduplicate identical-geometry components
    # (Array/Mirror copies). Apply a deterministic per-component grid pack so
    # every connected component gets its own UV slot. No-op for single-component
    # meshes.
    _grid_pack_components(me, margin)

    for layer in me.uv_layers:
        layer.active_render = layer.name == uv0_name

    return True


def _resolve_asset_density(
    asset_coll: bpy.types.Collection, prop_name: str, default_density: float
) -> float:
    """Return target texel density for an asset (custom prop on asset root wins)."""
    raw = asset_coll.get(prop_name)
    if raw is None:
        return default_density
    try:
        val = float(raw)
        if val > 0.0:
            return val
    except (TypeError, ValueError):
        pass
    return default_density


def _export_collection_as_glb(
    asset_coll: bpy.types.Collection,
    output_path: str,
    warnings: list[str],
    *,
    apply_modifiers: bool = True,
    export_tangents: bool = True,
    export_materials: str = "EXPORT",
    bake_uv2: bool = False,
    uv2_method: str = "smart",
    uv2_margin: float = 0.02,
    target_texel_density: float = 4.0,
    lightmap_texel_density_prop: str = "lightmap_texel_density",
) -> dict[str, Any]:
    """Select all objects in *asset_coll* (recursively) and export as GLB.

    Returns a dict with keys: success (bool), uv2_baked (int), uv2_skipped (int),
    lightmap_texel_size (float | None).
    """
    stats: dict[str, Any] = {
        "success": False,
        "uv2_baked": 0,
        "uv2_skipped": 0,
        "lightmap_texel_size": None,
    }

    all_objs = list(asset_coll.all_objects)
    if not all_objs:
        warnings.append(f"Asset '{asset_coll.name}' has no objects — skipping export.")
        return stats

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

    swap_records: list[tuple[bpy.types.Object, bpy.types.Object, bpy.types.Mesh, bpy.types.Collection]] = []
    stamped_texel_objects: list[tuple[bpy.types.Object, Any]] = []
    texel_size_used: float | None = None

    if bake_uv2:
        density = _resolve_asset_density(asset_coll, lightmap_texel_density_prop, target_texel_density)
        if density <= 0.0:
            density = target_texel_density if target_texel_density > 0.0 else 4.0
        texel_size_used = 1.0 / density
        stats["lightmap_texel_size"] = texel_size_used
        depsgraph = bpy.context.evaluated_depsgraph_get()
        n_baked = 0
        n_skipped = 0
        for orig in _iter_visual_mesh_objects(asset_coll):
            owning = _find_owning_collection(orig, asset_coll)
            if owning is None:
                warnings.append(
                    f"[{asset_coll.name}] {orig.name}: no owning collection found under asset — UV2 skipped."
                )
                continue

            had_pre_existing_uv2 = orig.data is not None and len(orig.data.uv_layers) >= 2
            try:
                new_obj, me_eval = _bake_evaluated_copy(orig, depsgraph, owning)
            except Exception as exc:  # noqa: BLE001
                warnings.append(
                    f"[{asset_coll.name}] {orig.name}: modifier bake failed: {exc}"
                )
                continue
            swap_records.append((orig, new_obj, me_eval, owning))

            if had_pre_existing_uv2:
                n_skipped += 1
                warnings.append(
                    f"[{asset_coll.name}] {orig.name}: skipped UV2 unwrap (mesh already has >=2 UV layers)."
                )
            else:
                if _ensure_uv2(new_obj, uv2_method, uv2_margin, warnings, asset_coll.name):
                    n_baked += 1
                else:
                    n_skipped += 1

            stamped_texel_objects.append((new_obj, new_obj.get("lightmap_texel_size")))
            if "lightmap_texel_size" not in new_obj:
                new_obj["lightmap_texel_size"] = texel_size_used

        stats["uv2_baked"] = n_baked
        stats["uv2_skipped"] = n_skipped

    all_objs_after_swap = list(asset_coll.all_objects)

    for obj in bpy.data.objects:
        obj.select_set(False)

    hide_states: dict[str, tuple[bool, bool]] = {}
    selected: list[bpy.types.Object] = []
    skipped_not_in_view_layer: list[str] = []
    for obj in all_objs_after_swap:
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

    try:
        if not selected:
            warnings.append(
                f"Asset '{asset_coll.name}' has no selectable objects in active ViewLayer — skipping export."
            )
        else:
            bpy.context.view_layer.objects.active = selected[0]
            export_apply = False if bake_uv2 else apply_modifiers
            try:
                bpy.ops.export_scene.gltf(
                    filepath=output_path,
                    export_format="GLB",
                    use_selection=True,
                    export_extras=True,
                    export_yup=True,
                    export_materials=export_materials,
                    export_apply=export_apply,
                    export_tangents=export_tangents,
                    export_texcoords=True,
                    export_normals=True,
                    export_animations=True,
                )
                stats["success"] = True
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"glTF export failed for '{asset_coll.name}': {exc}")
    finally:
        for obj in all_objs_after_swap:
            if obj.name in hide_states:
                obj.hide_viewport, obj.hide_render = hide_states[obj.name]

        for orig, new_obj, me_eval, owning in reversed(swap_records):
            try:
                if new_obj.name in owning.objects:
                    owning.objects.unlink(new_obj)
            except Exception:  # noqa: BLE001
                pass
            try:
                if orig.name not in owning.objects:
                    owning.objects.link(orig)
            except Exception:  # noqa: BLE001
                pass
            try:
                bpy.data.objects.remove(new_obj, do_unlink=True)
            except Exception:  # noqa: BLE001
                pass
            try:
                bpy.data.meshes.remove(me_eval, do_unlink=True)
            except Exception:  # noqa: BLE001
                pass

        for lc, exclude, hide_vp in saved_layer_state:
            try:
                lc.exclude = exclude
                lc.hide_viewport = hide_vp
            except Exception:  # noqa: BLE001
                pass

    return stats


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

    bake_uv2 = bool(payload.get("bake_uv2", False))
    uv2_method_raw = str(payload.get("uv2_method", "smart") or "smart").lower()
    uv2_method = uv2_method_raw if uv2_method_raw in {"smart", "lightmap_pack"} else "smart"
    try:
        uv2_margin = float(payload.get("uv2_margin", 0.02))
    except (TypeError, ValueError):
        uv2_margin = 0.02
    if uv2_margin < 0.0:
        uv2_margin = 0.02
    try:
        target_texel_density = float(payload.get("target_texel_density", 4.0))
    except (TypeError, ValueError):
        target_texel_density = 4.0
    if target_texel_density <= 0.0:
        target_texel_density = 4.0
    lightmap_texel_density_prop = str(
        payload.get("lightmap_texel_density_prop", "lightmap_texel_density")
        or "lightmap_texel_density"
    )

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
        stats = _export_collection_as_glb(
            asset_coll,
            glb_path,
            warnings,
            apply_modifiers=apply_modifiers,
            export_tangents=export_tangents,
            export_materials=export_materials,
            bake_uv2=bake_uv2,
            uv2_method=uv2_method,
            uv2_margin=uv2_margin,
            target_texel_density=target_texel_density,
            lightmap_texel_density_prop=lightmap_texel_density_prop,
        )
        entry: dict[str, Any] = {
            "asset": name,
            "path": glb_path,
            "status": "exported" if stats["success"] else "failed",
            "uv2_baked_meshes": int(stats.get("uv2_baked", 0)),
            "uv2_skipped_meshes": int(stats.get("uv2_skipped", 0)),
            "lightmap_texel_size": stats.get("lightmap_texel_size"),
        }
        if stats["success"]:
            n_exported += 1
        else:
            n_failed += 1
        exported.append(entry)

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
