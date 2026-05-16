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


def _uv_islands(me: bpy.types.Mesh) -> dict[int, list[int]]:
    """Return polygon-index lists keyed by UV-island root.

    Two polygons are in the same UV island iff they share an **edge** (3D vertex
    pair) AND store identical UV2 coords at both endpoints (no UV seam between
    them). Matches Blender's UV editor "island" definition.

    This is what we want to pack — NOT vertex-connected components. A single
    cube is one component but smart_project typically splits it into 1-6 UV
    islands; packing only the component AABB wastes most of the unit square.
    """
    if len(me.uv_layers) < 2 or len(me.polygons) == 0:
        return {}
    uv_layer = me.uv_layers[1].data
    n_polys = len(me.polygons)
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

    quant = 1.0 / 1e-5
    edge_bucket: dict[tuple[int, int, int, int, int, int], int] = {}
    for pi, poly in enumerate(me.polygons):
        verts = list(poly.vertices)
        loops = list(poly.loop_indices)
        n = len(verts)
        for i in range(n):
            v0 = int(verts[i])
            v1 = int(verts[(i + 1) % n])
            uv0 = uv_layer[loops[i]].uv
            uv1 = uv_layer[loops[(i + 1) % n]].uv
            if v0 < v1:
                v_min, v_max = v0, v1
                uv_lo, uv_hi = uv0, uv1
            else:
                v_min, v_max = v1, v0
                uv_lo, uv_hi = uv1, uv0
            key = (
                v_min,
                v_max,
                int(round(uv_lo.x * quant)),
                int(round(uv_lo.y * quant)),
                int(round(uv_hi.x * quant)),
                int(round(uv_hi.y * quant)),
            )
            other = edge_bucket.get(key)
            if other is None:
                edge_bucket[key] = pi
            else:
                union(pi, other)

    islands: dict[int, list[int]] = {}
    for pi in range(n_polys):
        islands.setdefault(find(pi), []).append(pi)
    return islands


def _shelf_pack(
    rects: list[tuple[float, float]], margin: float, scale: float
) -> list[tuple[float, float]] | None:
    """First-Fit-Decreasing-Height shelf packer.

    *rects* must already be sorted by height descending. Returns a list of
    (offset_u, offset_v) for each rect at the same index, or None if any rect
    fails to fit inside [margin, 1-margin]^2 at the given scale.
    """
    avail = 1.0 - 2.0 * margin
    if avail <= 0.0:
        return None
    positions: list[tuple[float, float]] = [(0.0, 0.0)] * len(rects)
    cur_x = margin
    cur_y = margin
    shelf_h = 0.0
    for i, (w, h) in enumerate(rects):
        sw = w * scale + margin
        sh = h * scale + margin
        if sw > avail + 1e-9 or sh > avail + 1e-9:
            return None
        if cur_x + sw > 1.0 - margin + 1e-9:
            cur_y += shelf_h
            cur_x = margin
            shelf_h = 0.0
        if cur_y + sh > 1.0 - margin + 1e-9:
            return None
        positions[i] = (cur_x, cur_y)
        cur_x += sw
        if sh > shelf_h:
            shelf_h = sh
    return positions


def _uniform_fit_uv2_layout(me: bpy.types.Mesh, margin: float) -> None:
    """Uniformly scale + translate all UV2 loops so the mesh AABB fills [margin, 1-margin]^2.

    Preserves every island's relative size and spacing from smart_project /
    average_islands_scale. This is the only scaling step in fill-square mode.
    """
    if len(me.uv_layers) < 2 or len(me.polygons) == 0:
        return
    uv_layer = me.uv_layers[1].data
    u_min = v_min = float("inf")
    u_max = v_max = float("-inf")
    for poly in me.polygons:
        for li in poly.loop_indices:
            uv = uv_layer[li].uv
            if uv.x < u_min:
                u_min = uv.x
            if uv.y < v_min:
                v_min = uv.y
            if uv.x > u_max:
                u_max = uv.x
            if uv.y > v_max:
                v_max = uv.y
    bb_w = max(u_max - u_min, 1e-6)
    bb_h = max(v_max - v_min, 1e-6)
    target = max(1.0 - 2.0 * margin, 0.01)
    scale = min(target / bb_w, target / bb_h)
    new_w = bb_w * scale
    new_h = bb_h * scale
    off_u = margin + (target - new_w) * 0.5 - u_min * scale
    off_v = margin + (target - new_h) * 0.5 - v_min * scale
    for poly in me.polygons:
        for li in poly.loop_indices:
            uv = uv_layer[li].uv
            uv_layer[li].uv = (uv.x * scale + off_u, uv.y * scale + off_v)


def _pack_islands_manual(me: bpy.types.Mesh, margin: float) -> None:
    """Lay out UV2 islands without resizing them individually.

    Replaces ``bpy.ops.uv.pack_islands`` because the operator stacks
    identical-shape islands (Array / Mirror copies) on top of each other.

    Island sizes come from smart_project and, in density mode,
  average_islands_scale. This pass only translates islands (optional 90°
    rotation for shelf packing) and applies one shared scale factor so
    everything fits in [0, 1]^2.
    """
    if len(me.uv_layers) < 2 or len(me.polygons) == 0:
        return
    islands = _uv_islands(me)
    if not islands:
        return

    uv_layer = me.uv_layers[1].data
    info: list[dict[str, Any]] = []
    for _root, pis in sorted(islands.items()):
        mn_u = mn_v = float("inf")
        mx_u = mx_v = float("-inf")
        for pi in pis:
            poly = me.polygons[pi]
            for li in poly.loop_indices:
                p = uv_layer[li].uv
                if p.x < mn_u:
                    mn_u = p.x
                if p.y < mn_v:
                    mn_v = p.y
                if p.x > mx_u:
                    mx_u = p.x
                if p.y > mx_v:
                    mx_v = p.y
        bb_w = max(mx_u - mn_u, 1e-6)
        bb_h = max(mx_v - mn_v, 1e-6)
        if bb_h > bb_w:
            info.append(
                {
                    "pis": pis,
                    "mn_u": mn_u,
                    "mn_v": mn_v,
                    "bb_w": bb_w,
                    "bb_h": bb_h,
                    "rotate": True,
                    "target_w": bb_h,
                    "target_h": bb_w,
                }
            )
        else:
            info.append(
                {
                    "pis": pis,
                    "mn_u": mn_u,
                    "mn_v": mn_v,
                    "bb_w": bb_w,
                    "bb_h": bb_h,
                    "rotate": False,
                    "target_w": bb_w,
                    "target_h": bb_h,
                }
            )

    info.sort(key=lambda c: c["target_h"], reverse=True)
    rects = [(c["target_w"], c["target_h"]) for c in info]

    lo, hi = 1e-9, 1e6
    best_positions: list[tuple[float, float]] | None = None
    best_scale = lo
    for _ in range(60):
        mid = (lo + hi) * 0.5
        pos = _shelf_pack(rects, margin, mid)
        if pos is not None:
            best_positions = pos
            best_scale = mid
            lo = mid
        else:
            hi = mid
    if best_positions is None:
        import math

        n = len(info)
        cols = max(1, math.ceil(math.sqrt(n)))
        cw = (1.0 - 2.0 * margin) / cols
        rows = max(1, math.ceil(n / cols))
        ch = (1.0 - 2.0 * margin) / rows
        best_scale = min(
            cw / max(c["target_w"] for c in info),
            ch / max(c["target_h"] for c in info),
        )
        best_positions = []
        for i in range(n):
            r, col = divmod(i, cols)
            best_positions.append((margin + col * cw, margin + r * ch))

    for i, c in enumerate(info):
        off_u, off_v = best_positions[i]
        final_w = c["target_w"] * best_scale
        final_h = c["target_h"] * best_scale
        if c["rotate"]:
            # 90° CCW: (x_local, y_local) -> (bb_h - y_local, x_local)
            # then scale post-rot bbox (bb_h × bb_w) to (final_w × final_h).
            sx = final_w / c["bb_h"]
            sy = final_h / c["bb_w"]
            for pi in c["pis"]:
                for li in me.polygons[pi].loop_indices:
                    p = uv_layer[li].uv
                    xl = p.x - c["mn_u"]
                    yl = p.y - c["mn_v"]
                    uv_layer[li].uv = (
                        (c["bb_h"] - yl) * sx + off_u,
                        xl * sy + off_v,
                    )
        else:
            sx = final_w / c["bb_w"]
            sy = final_h / c["bb_h"]
            for pi in c["pis"]:
                for li in me.polygons[pi].loop_indices:
                    p = uv_layer[li].uv
                    uv_layer[li].uv = (
                        (p.x - c["mn_u"]) * sx + off_u,
                        (p.y - c["mn_v"]) * sy + off_v,
                    )


def _ensure_uv2(
    obj: bpy.types.Object,
    method: str,
    margin: float,
    fill_square: bool,
    warnings: list[str],
    asset_name: str,
) -> bool:
    """Add and unwrap a UV2 layer on *obj* in place. Return True if a layer was baked.

    Pipeline (in order):

      1. Initial projection — smart_project (default) or lightmap_pack.
      2. Density mode only — average_islands_scale (Blender sizes islands by
         3D surface area; no per-island rescaling in our packer).
      3. _pack_islands_manual — translate islands into [0,1]^2 with one
         shared scale factor. Replaces bpy.ops.uv.pack_islands, which stacks
         identical-shape Array / Mirror copies on top of each other.
      4. Fill-square mode only — _uniform_fit_uv2_layout stretches the whole
         layout uniformly to fill [margin, 1-margin]^2.
    """
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
        if not fill_square:
            bpy.ops.uv.average_islands_scale()
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"[{asset_name}] {obj.name}: UV2 unwrap failed: {exc}")
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:  # noqa: BLE001
            pass
        return False
    finally:
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:  # noqa: BLE001
            pass

    _pack_islands_manual(me, margin)
    if fill_square:
        _uniform_fit_uv2_layout(me, margin)

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
    uv2_margin: float = 0.005,
    uv2_fill_square: bool = False,
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
                if _ensure_uv2(new_obj, uv2_method, uv2_margin, uv2_fill_square, warnings, asset_coll.name):
                    n_baked += 1
                else:
                    n_skipped += 1

            stamped_texel_objects.append((new_obj, new_obj.get("lightmap_texel_size")))
            if "lightmap_texel_size" not in new_obj:
                new_obj["lightmap_texel_size"] = texel_size_used

        stats["uv2_baked"] = n_baked
        stats["uv2_skipped"] = n_skipped

    name_swaps: list[tuple[bpy.types.Object, str, bpy.types.Object, str]] = []
    if bake_uv2 and swap_records:
        # Phase 2: re-parent baked copies whose parent was also swapped, otherwise
        # the glTF exporter silently drops them (it only emits objects whose entire
        # parent chain is in the selection).
        orig_to_new: dict[str, bpy.types.Object] = {rec[0].name: rec[1] for rec in swap_records}
        for _orig, new_obj, _me, _own in swap_records:
            p = new_obj.parent
            if p is not None and p.name in orig_to_new:
                new_parent = orig_to_new[p.name]
                world = new_obj.matrix_world.copy()
                new_obj.parent = new_parent
                new_obj.parent_type = _orig.parent_type
                new_obj.parent_bone = _orig.parent_bone
                new_obj.matrix_world = world

        # Phase 3: swap names so the glTF gets the *original* clean names. We rename
        # originals to <name>__uv2orig and rename baked copies to the original names.
        # We restore both names in the finally block.
        for orig, new_obj, _me, _own in swap_records:
            clean = orig.name
            baked_name = new_obj.name
            tmp_orig_name = f"{clean}__uv2orig"
            # First move the original out of the way (orig is not linked to any
            # asset collection at this point, but still owns the name).
            orig.name = tmp_orig_name
            new_obj.name = clean
            name_swaps.append((orig, clean, new_obj, baked_name))

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
            # Always honor apply_modifiers here. UV2-baked duplicates already have
            # modifiers cleared and evaluated geometry in .data — export_apply is a
            # no-op for them. Setting export_apply=False (old behavior) skipped
            # modifier baking for *all* selected objects (collision, helpers, etc.),
            # which desynced mesh from materials / tangents and caused transparent or
            # wrong surfaces in Godot after import.
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
                stats["success"] = True
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"glTF export failed for '{asset_coll.name}': {exc}")
    finally:
        for obj in all_objs_after_swap:
            if obj.name in hide_states:
                obj.hide_viewport, obj.hide_render = hide_states[obj.name]

        # Reverse the name swap before unlinking baked copies so the original
        # objects (which we're about to relink into the source .blend) reclaim
        # their original names.
        for orig, clean_name, new_obj, baked_name in reversed(name_swaps):
            try:
                new_obj.name = baked_name
            except Exception:  # noqa: BLE001
                pass
            try:
                orig.name = clean_name
            except Exception:  # noqa: BLE001
                pass

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
        uv2_margin = float(payload.get("uv2_margin", 0.005))
    except (TypeError, ValueError):
        uv2_margin = 0.005
    if uv2_margin < 0.0:
        uv2_margin = 0.005
    uv2_fill_square = bool(payload.get("uv2_fill_square", False))
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
            uv2_fill_square=uv2_fill_square,
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
