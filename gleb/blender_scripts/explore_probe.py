"""Explore data inside a .blend file using bpy."""

from __future__ import annotations

from pathlib import Path
import sys

import bpy

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _shared import decode_payload_from_argv, dump_json_line  # noqa: E402

ALL_SCOPES = {
    "scene",
    "collections",
    "objects",
    "materials",
    "modifiers",
    "animations",
    "relations",
    "constraints",
    "geometry",
    "textures",
    "armatures",
    "libraries",
    "custom_properties",
}


def _matches(name: str, targets: list[str], mode: str, ignore_case: bool) -> bool:
    if not targets:
        return True
    candidate = name.lower() if ignore_case else name
    prepared = [t.lower() if ignore_case else t for t in targets]
    if mode == "exact":
        return any(candidate == t for t in prepared)
    if mode == "contains":
        return any(t in candidate for t in prepared)
    if mode == "regex":
        import re

        return any(re.search(t, candidate) is not None for t in prepared)
    return False


def _collect_scene() -> dict:
    scene = bpy.context.scene
    return {"name": scene.name, "frame_start": scene.frame_start, "frame_end": scene.frame_end}


def _poly_breakdown(mesh) -> dict[str, int]:
    tris = 0
    quads = 0
    ngons = 0
    for poly in mesh.polygons:
        verts = len(poly.vertices)
        if verts == 3:
            tris += 1
        elif verts == 4:
            quads += 1
        elif verts > 4:
            ngons += 1
    return {"tris": tris, "quads": quads, "ngons": ngons}


def _as_json_primitive(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_as_json_primitive(v) for v in value]
    if hasattr(value, "to_list"):
        try:
            return [_as_json_primitive(v) for v in value.to_list()]
        except Exception:
            return str(value)
    if hasattr(value, "__iter__") and not isinstance(value, (dict, str, bytes)):
        try:
            return [_as_json_primitive(v) for v in value]
        except Exception:
            return str(value)
    if hasattr(value, "name"):
        try:
            return str(value.name)
        except Exception:
            return str(value)
    return str(value)


def _safe_prop(owner, prop) -> object:
    identifier = getattr(prop, "identifier", "")
    if identifier in {"rna_type"}:
        return None
    if identifier.startswith("bl_"):
        return None
    if getattr(prop, "is_readonly", False):
        return None
    try:
        value = getattr(owner, identifier)
    except Exception:
        return None
    return _as_json_primitive(value)


def _collect_settings(owner) -> dict[str, object]:
    settings: dict[str, object] = {}
    for prop in owner.rna_type.properties:
        identifier = getattr(prop, "identifier", "")
        if identifier in {"rna_type", "name", "type"}:
            continue
        value = _safe_prop(owner, prop)
        if value is not None:
            settings[identifier] = value
    return settings


def _collect_geometry(object_names: list[str], match: str, ignore_case: bool, detail: bool) -> list[dict]:
    output = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if not _matches(obj.name, object_names, match, ignore_case):
            continue
        mesh = obj.data
        breakdown = _poly_breakdown(mesh)
        edge_face_use: dict[tuple[int, int], int] = {}
        for poly in mesh.polygons:
            for edge_key in poly.edge_keys:
                edge_face_use[edge_key] = edge_face_use.get(edge_key, 0) + 1
        entry = {
            "object": obj.name,
            "verts": len(mesh.vertices),
            "edges": len(mesh.edges),
            "polys": len(mesh.polygons),
            "tris": breakdown["tris"],
            "quads": breakdown["quads"],
            "ngons": breakdown["ngons"],
            "uv_layers": [layer.name for layer in mesh.uv_layers],
            "vertex_colors": [layer.name for layer in mesh.color_attributes],
            "shape_keys": len(mesh.shape_keys.key_blocks) if mesh.shape_keys else 0,
            "is_manifold": all(use_count <= 2 for use_count in edge_face_use.values()),
            "has_loose_geometry": any(edge.is_loose for edge in mesh.edges),
        }
        if detail:
            entry["materials"] = [mat.name for mat in mesh.materials if mat]
            entry["users"] = mesh.users
        output.append(entry)
    return output


def _collect_textures(detail: bool) -> list[dict]:
    output = []
    for image in bpy.data.images:
        is_missing = bool(image.source == "FILE" and image.filepath and not image.has_data and not image.packed_file)
        entry = {
            "name": image.name,
            "source": image.source,
            "filepath": image.filepath,
            "packed": bool(image.packed_file),
            "missing": is_missing,
            "colorspace": image.colorspace_settings.name if image.colorspace_settings else None,
            "size": [int(image.size[0]), int(image.size[1])] if image.size else [0, 0],
        }
        if detail:
            entry["alpha_mode"] = image.alpha_mode
            entry["generated_type"] = image.generated_type
        output.append(entry)
    return output


def _collect_armatures(object_names: list[str], match: str, ignore_case: bool, detail: bool) -> list[dict]:
    output = []
    for obj in bpy.data.objects:
        if obj.type != "ARMATURE":
            continue
        if not _matches(obj.name, object_names, match, ignore_case):
            continue
        arm_data = obj.data
        entry = {
            "object": obj.name,
            "bones": len(arm_data.bones),
            "deform_bones": sum(1 for b in arm_data.bones if b.use_deform),
            "has_animation": bool(obj.animation_data and obj.animation_data.action),
            "action": obj.animation_data.action.name if obj.animation_data and obj.animation_data.action else None,
        }
        if detail:
            entry["bone_names"] = [b.name for b in arm_data.bones]
        output.append(entry)
    return output


def _collect_libraries() -> list[dict]:
    output = []
    for lib in bpy.data.libraries:
        output.append(
            {
                "name": lib.name,
                "filepath": lib.filepath,
                "is_missing": not Path(bpy.path.abspath(lib.filepath)).exists() if lib.filepath else False,
            }
        )
    return output


def _collect_custom_properties(object_names: list[str], match: str, ignore_case: bool) -> list[dict]:
    output = []

    def collect_for_item(item_name: str, item, kind: str) -> None:
        props = {}
        for key in item.keys():
            if key.startswith("_"):
                continue
            props[key] = _as_json_primitive(item.get(key))
        if props:
            output.append({"kind": kind, "name": item_name, "properties": props})

    collect_for_item(bpy.context.scene.name, bpy.context.scene, "scene")
    for coll in bpy.data.collections:
        collect_for_item(coll.name, coll, "collection")
    for obj in bpy.data.objects:
        if not _matches(obj.name, object_names, match, ignore_case):
            continue
        collect_for_item(obj.name, obj, "object")
        if any(suffix in obj.name for suffix in ["-col", "-colonly", "--lod"]):
            output.append({"kind": "object", "name": obj.name, "godot_hint": True, "properties": {}})

    return output


def _add_diagnostic(
    items: list[dict], severity: str, code: str, message: str, scope: str, object_name: str | None = None, data: dict | None = None
) -> None:
    payload = {
        "severity": severity,
        "code": code,
        "message": message,
        "scope": scope,
        "data": data or {},
    }
    if object_name:
        payload["object"] = object_name
    items.append(payload)


def _collect_diagnostics(data: dict[str, object]) -> list[dict]:
    diagnostics: list[dict] = []

    collections = data.get("structure", {}).get("collections", []) if isinstance(data.get("structure"), dict) else []
    objects = data.get("objects", []) if isinstance(data.get("objects"), list) else []
    geometry = data.get("geometry", []) if isinstance(data.get("geometry"), list) else []
    textures = data.get("textures", []) if isinstance(data.get("textures"), list) else []
    libraries = data.get("libraries", []) if isinstance(data.get("libraries"), list) else []
    modifiers = data.get("modifiers", []) if isinstance(data.get("modifiers"), list) else []

    for coll in collections:
        if int(coll.get("object_count", 0)) == 0 and not coll.get("child_collections"):
            _add_diagnostic(diagnostics, "info", "EMPTY_COLLECTION", "Collection has no objects and no children.", "collections", coll.get("name"))

    for obj in objects:
        if not obj.get("collections"):
            _add_diagnostic(diagnostics, "warning", "OBJECT_NOT_IN_COLLECTION", "Object is not assigned to a collection.", "objects", obj.get("name"))
        transforms = obj.get("transforms", {})
        if isinstance(transforms, dict):
            scale = transforms.get("scale")
            if isinstance(scale, list) and any(abs(float(v) - 1.0) > 1e-4 for v in scale):
                _add_diagnostic(diagnostics, "warning", "UNAPPLIED_SCALE", "Object scale is not applied.", "objects", obj.get("name"), {"scale": scale})
            if isinstance(scale, list) and any(float(v) < 0 for v in scale):
                _add_diagnostic(diagnostics, "warning", "NEGATIVE_SCALE", "Object has negative scale.", "objects", obj.get("name"), {"scale": scale})

    for item in geometry:
        if int(item.get("ngons", 0)) > 0:
            _add_diagnostic(diagnostics, "warning", "NGON_PRESENT", "Mesh contains ngons.", "geometry", item.get("object"), {"ngons": item.get("ngons")})
        if int(item.get("polys", 0)) > 15000:
            _add_diagnostic(diagnostics, "warning", "HIGH_POLY_COUNT", "Mesh has high polygon count.", "geometry", item.get("object"), {"polys": item.get("polys")})
        if item.get("materials") and not item.get("uv_layers"):
            _add_diagnostic(diagnostics, "warning", "NO_UV_LAYER", "Mesh has materials but no UV layer.", "geometry", item.get("object"))
        if int(item.get("shape_keys", 0)) > 0:
            _add_diagnostic(diagnostics, "info", "HAS_SHAPE_KEYS", "Mesh has shape keys.", "geometry", item.get("object"))

    for image in textures:
        if image.get("missing"):
            _add_diagnostic(diagnostics, "error", "MISSING_TEXTURE_FILE", "Texture file appears missing/unloaded.", "textures", data={"name": image.get("name"), "filepath": image.get("filepath")})
        elif not image.get("packed"):
            _add_diagnostic(diagnostics, "info", "UNPACKED_TEXTURES", "Texture is external (not packed).", "textures", data={"name": image.get("name")})

    for mod in modifiers:
        if mod.get("type") == "NODES":
            _add_diagnostic(diagnostics, "info", "GEOMETRY_NODES_MODIFIER_PRESENT", "Geometry Nodes modifier present; verify glTF export expectations.", "modifiers", mod.get("object"), {"modifier": mod.get("name")})

    for lib in libraries:
        _add_diagnostic(diagnostics, "info", "LINKED_LIBRARY_PRESENT", "File uses linked Blender library.", "libraries", data={"filepath": lib.get("filepath")})
        if lib.get("is_missing"):
            _add_diagnostic(diagnostics, "error", "MISSING_LIBRARY_FILE", "Linked library file is missing.", "libraries", data={"filepath": lib.get("filepath")})

    return diagnostics


def _collect_collections() -> list[dict]:
    output = []
    for coll in bpy.data.collections:
        output.append(
            {
                "name": coll.name,
                "object_count": len(coll.objects),
                "child_collections": [c.name for c in coll.children],
            }
        )
    return output


def _collect_objects(object_names: list[str], match: str, ignore_case: bool, detail: bool) -> list[dict]:
    output = []
    for obj in bpy.data.objects:
        if not _matches(obj.name, object_names, match, ignore_case):
            continue
        entry = {
            "name": obj.name,
            "type": obj.type,
            "collections": [c.name for c in obj.users_collection],
            "materials": [slot.material.name for slot in obj.material_slots if slot.material],
            "modifiers": [mod.name for mod in obj.modifiers],
            "constraints": [con.name for con in obj.constraints],
            "has_animation": bool(obj.animation_data and obj.animation_data.action),
            "data_block": obj.data.name if obj.data else None,
        }
        if detail:
            entry["transforms"] = {
                "location": _as_json_primitive(obj.location),
                "rotation_euler": _as_json_primitive(obj.rotation_euler),
                "rotation_quaternion": _as_json_primitive(obj.rotation_quaternion),
                "rotation_mode": obj.rotation_mode,
                "scale": _as_json_primitive(obj.scale),
                "dimensions": _as_json_primitive(obj.dimensions),
            }
        output.append(entry)
    return output


def _collect_materials() -> list[dict]:
    output = []
    for mat in bpy.data.materials:
        output.append(
            {
                "name": mat.name,
                "use_nodes": mat.use_nodes,
                "node_count": len(mat.node_tree.nodes) if mat.node_tree else 0,
            }
        )
    return output


def _collect_modifiers(object_names: list[str], match: str, ignore_case: bool, detail: bool) -> list[dict]:
    output = []
    for obj in bpy.data.objects:
        if not _matches(obj.name, object_names, match, ignore_case):
            continue
        for mod in obj.modifiers:
            entry = {"object": obj.name, "name": mod.name, "type": mod.type}
            if detail:
                entry["settings"] = _collect_settings(mod)
            output.append(entry)
    return output


def _collect_constraints(object_names: list[str], match: str, ignore_case: bool, detail: bool) -> list[dict]:
    output = []
    for obj in bpy.data.objects:
        if not _matches(obj.name, object_names, match, ignore_case):
            continue
        for con in obj.constraints:
            entry = {
                "object": obj.name,
                "name": con.name,
                "type": con.type,
                "influence": con.influence,
                "mute": con.mute,
            }
            if detail:
                entry["settings"] = _collect_settings(con)
            output.append(entry)
    return output


def _collect_animations(object_names: list[str], match: str, ignore_case: bool) -> list[dict]:
    output = []
    for obj in bpy.data.objects:
        if not _matches(obj.name, object_names, match, ignore_case):
            continue
        action_name = None
        if obj.animation_data and obj.animation_data.action:
            action_name = obj.animation_data.action.name
        if action_name:
            output.append({"object": obj.name, "action": action_name})
    return output


def _collect_relations(object_names: list[str], match: str, ignore_case: bool) -> list[dict]:
    output = []
    for obj in bpy.data.objects:
        if not _matches(obj.name, object_names, match, ignore_case):
            continue
        output.append(
            {
                "object": obj.name,
                "parent": obj.parent.name if obj.parent else None,
                "children": [child.name for child in obj.children],
            }
        )
    return output


def main() -> None:
    payload = decode_payload_from_argv()
    scope = payload.get("scope", "all")
    query = payload.get("query", {}) if isinstance(payload.get("query", {}), dict) else {}
    object_names = query.get("object_names", []) if isinstance(query.get("object_names", []), list) else []
    object_names = [str(v) for v in object_names]
    match = str(query.get("match", "exact"))
    ignore_case = bool(query.get("ignore_case", False))
    detail = bool(payload.get("detail", False))
    diagnose = bool(payload.get("diagnose", False))

    requested = ALL_SCOPES if scope == "all" else {scope}
    structure: dict[str, object] = {"collections": [], "relations": []}
    data: dict[str, object] = {"structure": structure}
    warnings: list[str] = []

    if scope != "all" and scope not in ALL_SCOPES:
        warnings.append(f"Unknown scope '{scope}', falling back to all.")
        requested = ALL_SCOPES

    if "collections" in requested:
        structure["collections"] = _collect_collections()
    if "relations" in requested:
        structure["relations"] = _collect_relations(object_names, match, ignore_case)
    if "scene" in requested:
        data["scene"] = _collect_scene()
    if "objects" in requested:
        data["objects"] = _collect_objects(object_names, match, ignore_case, detail)
    if "materials" in requested:
        data["materials"] = _collect_materials()
    if "modifiers" in requested:
        data["modifiers"] = _collect_modifiers(object_names, match, ignore_case, detail)
    if "constraints" in requested:
        data["constraints"] = _collect_constraints(object_names, match, ignore_case, detail)
    if "animations" in requested:
        data["animations"] = _collect_animations(object_names, match, ignore_case)
    if "geometry" in requested:
        data["geometry"] = _collect_geometry(object_names, match, ignore_case, detail)
    if "textures" in requested:
        data["textures"] = _collect_textures(detail)
    if "armatures" in requested:
        data["armatures"] = _collect_armatures(object_names, match, ignore_case, detail)
    if "libraries" in requested:
        data["libraries"] = _collect_libraries()
    if "custom_properties" in requested:
        data["custom_properties"] = _collect_custom_properties(object_names, match, ignore_case)
    if diagnose:
        data["diagnostics"] = _collect_diagnostics(data)
    summary = {
        "collections": len(structure.get("collections", []))
        if isinstance(structure.get("collections"), list)
        else 0,
        "relations": len(structure.get("relations", []))
        if isinstance(structure.get("relations"), list)
        else 0,
        "objects": len(data.get("objects", [])) if isinstance(data.get("objects"), list) else 0,
        "materials": len(data.get("materials", [])) if isinstance(data.get("materials"), list) else 0,
        "animations": len(data.get("animations", [])) if isinstance(data.get("animations"), list) else 0,
        "constraints": len(data.get("constraints", []))
        if isinstance(data.get("constraints"), list)
        else 0,
        "geometry": len(data.get("geometry", [])) if isinstance(data.get("geometry"), list) else 0,
        "textures": len(data.get("textures", [])) if isinstance(data.get("textures"), list) else 0,
        "armatures": len(data.get("armatures", [])) if isinstance(data.get("armatures"), list) else 0,
        "libraries": len(data.get("libraries", [])) if isinstance(data.get("libraries"), list) else 0,
        "custom_properties": len(data.get("custom_properties", []))
        if isinstance(data.get("custom_properties"), list)
        else 0,
        "diagnostics": len(data.get("diagnostics", []))
        if isinstance(data.get("diagnostics"), list)
        else 0,
    }

    dump_json_line(
        {
            "summary": summary,
            "data": data,
            "warnings": warnings,
            "errors": [],
        }
    )


if __name__ == "__main__":
    main()
