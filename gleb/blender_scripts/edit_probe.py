"""Apply structured edits to a .blend file using bpy."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import bpy

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _shared import decode_payload_from_argv, dump_json_line  # noqa: E402


def _ctx_temp_override(**kwargs: Any):
    """Build temp_override kwargs; add window when available (helps some operators)."""
    wm = bpy.context.window_manager
    if wm.windows:
        win = wm.windows[0]
        kwargs.setdefault("window", win)
    return bpy.context.temp_override(**kwargs)


def _object_by_name(name: str) -> bpy.types.Object | None:
    return bpy.data.objects.get(name)


def _material_by_name(name: str) -> bpy.types.Material | None:
    return bpy.data.materials.get(name)


def _mesh_materials(obj: bpy.types.Object) -> bpy.types.IDMaterials | None:
    data = getattr(obj, "data", None)
    if data is None:
        return None
    return getattr(data, "materials", None)


def _apply_modifier_settings(mod: bpy.types.Modifier, settings: dict[str, Any], warnings: list[str]) -> None:
    for key, val in settings.items():
        if not hasattr(mod, key):
            warnings.append(f"Unknown modifier property '{key}' on {mod.type} modifier '{mod.name}'.")
            continue
        try:
            setattr(mod, key, val)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Could not set modifier property '{key}': {exc}")


def _set_scene_property(path: str, value: Any) -> None:
    parts = path.split(".")
    target: Any = bpy.context.scene
    for part in parts[:-1]:
        target = getattr(target, part)
    setattr(target, parts[-1], value)


def _collection_by_name(name: str) -> bpy.types.Collection | None:
    return bpy.data.collections.get(name)


def _object_in_collection(obj: bpy.types.Object, coll: bpy.types.Collection) -> bool:
    return any(o is obj for o in coll.objects)


def _op_create_collection(op: dict[str, Any], dry_run: bool, warnings: list[str]) -> tuple[str, str]:
    name = str(op.get("name", ""))
    parent_name = op.get("parent")
    if not name:
        return "failed", "Missing 'name' for collection."
    if _collection_by_name(name) is not None:
        return "failed", f"Collection '{name}' already exists."
    if dry_run:
        extra = f" under '{parent_name}'" if parent_name else ""
        return "would_apply", f"Would create collection '{name}'{extra}."
    coll = bpy.data.collections.new(name)
    if parent_name:
        parent = _collection_by_name(str(parent_name))
        if parent is None:
            bpy.data.collections.remove(coll)
            return "failed", f"Parent collection '{parent_name}' not found."
        parent.children.link(coll)
    else:
        bpy.context.scene.collection.children.link(coll)
    return "applied", f"Created collection '{name}'."


def _op_rename_collection(op: dict[str, Any], dry_run: bool, warnings: list[str]) -> tuple[str, str]:
    old = str(op.get("from", ""))
    new = str(op.get("to", ""))
    coll = _collection_by_name(old)
    if coll is None:
        return "failed", f"Collection '{old}' not found."
    if old == new:
        return "skipped", f"Collection '{old}' already has target name."
    if _collection_by_name(new) is not None and _collection_by_name(new) != coll:
        return "failed", f"Target name '{new}' is already used by another collection."
    if dry_run:
        return "would_apply", f"Would rename collection '{old}' → '{new}'."
    coll.name = new
    return "applied", f"Renamed collection '{old}' → '{new}'."


def _op_link_object_to_collection(op: dict[str, Any], dry_run: bool, warnings: list[str]) -> tuple[str, str]:
    obj_name = str(op.get("object", ""))
    coll_name = str(op.get("collection", ""))
    obj = _object_by_name(obj_name)
    coll = _collection_by_name(coll_name)
    if obj is None:
        return "failed", f"Object '{obj_name}' not found."
    if coll is None:
        return "failed", f"Collection '{coll_name}' not found."
    if _object_in_collection(obj, coll):
        return "skipped", f"Object '{obj_name}' is already linked to '{coll_name}'."
    if dry_run:
        return "would_apply", f"Would link '{obj_name}' to collection '{coll_name}'."
    try:
        coll.objects.link(obj)
    except RuntimeError as exc:
        return "failed", str(exc)
    return "applied", f"Linked '{obj_name}' to collection '{coll_name}'."


def _op_unlink_object_from_collection(op: dict[str, Any], dry_run: bool, warnings: list[str]) -> tuple[str, str]:
    obj_name = str(op.get("object", ""))
    coll_name = str(op.get("collection", ""))
    obj = _object_by_name(obj_name)
    coll = _collection_by_name(coll_name)
    if obj is None:
        return "failed", f"Object '{obj_name}' not found."
    if coll is None:
        return "failed", f"Collection '{coll_name}' not found."
    if not _object_in_collection(obj, coll):
        return "skipped", f"Object '{obj_name}' is not linked to '{coll_name}'."
    if dry_run:
        return "would_apply", f"Would unlink '{obj_name}' from collection '{coll_name}'."
    if len(obj.users_collection) <= 1:
        return "failed", "Cannot unlink: object would not belong to any collection (link it elsewhere first)."
    try:
        coll.objects.unlink(obj)
    except RuntimeError as exc:
        return "failed", str(exc)
    return "applied", f"Unlinked '{obj_name}' from collection '{coll_name}'."


def _op_move_object_to_collection(op: dict[str, Any], dry_run: bool, warnings: list[str]) -> tuple[str, str]:
    obj_name = str(op.get("object", ""))
    from_name = str(op.get("from_collection", ""))
    to_name = str(op.get("to_collection", ""))
    obj = _object_by_name(obj_name)
    from_coll = _collection_by_name(from_name)
    to_coll = _collection_by_name(to_name)
    if obj is None:
        return "failed", f"Object '{obj_name}' not found."
    if from_coll is None:
        return "failed", f"Source collection '{from_name}' not found."
    if to_coll is None:
        return "failed", f"Target collection '{to_name}' not found."
    if from_coll is to_coll:
        return "skipped", "Source and target collection are the same."
    if not _object_in_collection(obj, from_coll):
        return "failed", f"Object '{obj_name}' is not in collection '{from_name}'."
    if dry_run:
        return "would_apply", f"Would move '{obj_name}' from '{from_name}' to '{to_name}'."
    if not _object_in_collection(obj, to_coll):
        to_coll.objects.link(obj)
    from_coll.objects.unlink(obj)
    return "applied", f"Moved '{obj_name}' from '{from_name}' to '{to_name}'."


def _op_create_object(op: dict[str, Any], dry_run: bool, warnings: list[str]) -> tuple[str, str]:
    name = str(op.get("name", ""))
    object_type = str(op.get("object_type", "MESH"))
    collection_name = op.get("collection")
    if not name:
        return "failed", "Missing 'name' for new object."
    if _object_by_name(name) is not None:
        return "failed", f"Object '{name}' already exists."
    if dry_run:
        return "would_apply", f"Would create {object_type} object '{name}'."
    if object_type == "MESH":
        mesh = bpy.data.meshes.new(f"{name}_MeshData")
        new_obj = bpy.data.objects.new(name, mesh)
    elif object_type == "EMPTY":
        new_obj = bpy.data.objects.new(name, None)
    else:
        return "failed", f"Unsupported object_type '{object_type}' (use MESH or EMPTY)."

    if collection_name is not None:
        coll = _collection_by_name(str(collection_name))
        if coll is None:
            mesh_data = new_obj.data if object_type == "MESH" else None
            bpy.data.objects.remove(new_obj, do_unlink=True)
            if mesh_data is not None:
                bpy.data.meshes.remove(mesh_data)
            return "failed", f"Collection '{collection_name}' not found."
        coll.objects.link(new_obj)
    else:
        bpy.context.scene.collection.objects.link(new_obj)
    return "applied", f"Created {object_type} object '{name}'."


def _op_rename_object(op: dict[str, Any], dry_run: bool, warnings: list[str]) -> tuple[str, str]:
    old = str(op.get("from", ""))
    new = str(op.get("to", ""))
    obj = _object_by_name(old)
    if obj is None:
        return "failed", f"Object '{old}' not found."
    if old == new:
        return "skipped", f"Object '{old}' already has target name."
    if _object_by_name(new) is not None and _object_by_name(new) != obj:
        return "failed", f"Target name '{new}' is already used by another object."
    if dry_run:
        return "would_apply", f"Would rename '{old}' → '{new}'."
    obj.name = new
    return "applied", f"Renamed '{old}' → '{new}'."


def _op_rename_material(op: dict[str, Any], dry_run: bool, warnings: list[str]) -> tuple[str, str]:
    old = str(op.get("from", ""))
    new = str(op.get("to", ""))
    mat = _material_by_name(old)
    if mat is None:
        return "failed", f"Material '{old}' not found."
    if old == new:
        return "skipped", f"Material '{old}' already has target name."
    if _material_by_name(new) is not None and _material_by_name(new) != mat:
        return "failed", f"Target name '{new}' is already used by another material."
    if dry_run:
        return "would_apply", f"Would rename material '{old}' → '{new}'."
    mat.name = new
    return "applied", f"Renamed material '{old}' → '{new}'."


def _op_join_objects(op: dict[str, Any], dry_run: bool, warnings: list[str]) -> tuple[str, str]:
    names = op.get("objects", [])
    if not isinstance(names, list) or len(names) < 2:
        return "failed", "'join_objects' requires 'objects' with at least two names."
    str_names = [str(n) for n in names]
    objs: list[bpy.types.Object] = []
    for n in str_names:
        o = _object_by_name(n)
        if o is None:
            return "failed", f"Object '{n}' not found for join."
        objs.append(o)
    if any(o.type != "MESH" for o in objs):
        return "failed", "All objects for join must be of type MESH."
    into = op.get("into")
    into_name = str(into) if into is not None else None
    base = objs[0]
    if dry_run:
        extra = f", result name '{into_name}'" if into_name else ""
        return "would_apply", f"Would join {len(objs)} mesh objects into '{base.name}'{extra}."
    view_layer = bpy.context.view_layer
    for o in bpy.data.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    view_layer.objects.active = base
    with _ctx_temp_override(
        active_object=base,
        selected_objects=objs,
        selected_editable_objects=objs,
        view_layer=view_layer,
    ):
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.join()
    if into_name:
        base.name = into_name
    return "applied", f"Joined {len(str_names)} objects into '{base.name}'."


def _op_delete_object(op: dict[str, Any], dry_run: bool, warnings: list[str]) -> tuple[str, str]:
    name = str(op.get("object", ""))
    obj = _object_by_name(name)
    if obj is None:
        return "failed", f"Object '{name}' not found."
    if dry_run:
        return "would_apply", f"Would delete object '{name}'."
    bpy.data.objects.remove(obj, do_unlink=True)
    return "applied", f"Deleted object '{name}'."


def _op_duplicate_object(op: dict[str, Any], dry_run: bool, warnings: list[str]) -> tuple[str, str]:
    name = str(op.get("object", ""))
    to = op.get("to")
    to_name = str(to) if to is not None else None
    obj = _object_by_name(name)
    if obj is None:
        return "failed", f"Object '{name}' not found."
    if dry_run:
        dest = to_name or f"{name}_copy"
        return "would_apply", f"Would duplicate '{name}' to '{dest}'."
    new_obj = obj.copy()
    if obj.data is not None:
        new_obj.data = obj.data.copy()
    bpy.context.scene.collection.objects.link(new_obj)
    if to_name:
        if _object_by_name(to_name) is not None:
            bpy.data.objects.remove(new_obj, do_unlink=True)
            return "failed", f"Target name '{to_name}' is already in use."
        new_obj.name = to_name
    return "applied", f"Duplicated '{name}' → '{new_obj.name}'."


def _op_add_modifier(op: dict[str, Any], dry_run: bool, warnings: list[str]) -> tuple[str, str]:
    obj_name = str(op.get("object", ""))
    mod_type = str(op.get("modifier_type", ""))
    obj = _object_by_name(obj_name)
    if obj is None:
        return "failed", f"Object '{obj_name}' not found."
    if not mod_type:
        return "failed", "Missing 'modifier_type'."
    mod_name = op.get("name")
    name_str = str(mod_name) if mod_name is not None else mod_type
    settings = op.get("settings", {})
    if settings is not None and not isinstance(settings, dict):
        return "failed", "'settings' must be an object."
    if dry_run:
        return "would_apply", f"Would add {mod_type} modifier '{name_str}' to '{obj_name}'."
    if name_str in obj.modifiers:
        return "failed", f"Modifier '{name_str}' already exists on '{obj_name}'."
    mod = obj.modifiers.new(name=name_str, type=mod_type)
    if settings:
        _apply_modifier_settings(mod, settings, warnings)
    return "applied", f"Added modifier '{mod.name}' ({mod_type}) to '{obj_name}'."


def _op_remove_modifier(op: dict[str, Any], dry_run: bool, warnings: list[str]) -> tuple[str, str]:
    obj_name = str(op.get("object", ""))
    mod_name = str(op.get("name", ""))
    obj = _object_by_name(obj_name)
    if obj is None:
        return "failed", f"Object '{obj_name}' not found."
    mod = obj.modifiers.get(mod_name)
    if mod is None:
        return "failed", f"Modifier '{mod_name}' not found on '{obj_name}'."
    if dry_run:
        return "would_apply", f"Would remove modifier '{mod_name}' from '{obj_name}'."
    obj.modifiers.remove(mod)
    return "applied", f"Removed modifier '{mod_name}' from '{obj_name}'."


def _op_apply_modifiers(op: dict[str, Any], dry_run: bool, warnings: list[str]) -> tuple[str, str]:
    obj_name = str(op.get("object", ""))
    names = op.get("names")
    obj = _object_by_name(obj_name)
    if obj is None:
        return "failed", f"Object '{obj_name}' not found."
    if names is not None and not isinstance(names, list):
        return "failed", "'names' must be an array of strings or null."
    if not names and not obj.modifiers:
        return "skipped", f"No modifiers to apply on '{obj_name}'."
    if dry_run:
        return "would_apply", f"Would apply modifiers on '{obj_name}'."
    if names:
        missing = [str(n) for n in names if obj.modifiers.get(str(n)) is None]
        if missing:
            return "failed", f"Modifiers not found: {', '.join(missing)}"
        mods = [obj.modifiers.get(str(n)) for n in names]
        mods = [m for m in mods if m is not None]
    else:
        mods = list(obj.modifiers)
    view_layer = bpy.context.view_layer
    for o in bpy.data.objects:
        o.select_set(False)
    obj.select_set(True)
    view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="OBJECT")
    with _ctx_temp_override(
        active_object=obj,
        selected_objects=[obj],
        selected_editable_objects=[obj],
        view_layer=view_layer,
    ):
        if names:
            for mod in mods:
                bpy.ops.object.modifier_apply(modifier=mod.name)
        else:
            while obj.modifiers:
                bpy.ops.object.modifier_apply(modifier=obj.modifiers[0].name)
    return "applied", f"Applied modifiers on '{obj_name}'."


def _op_set_material(op: dict[str, Any], dry_run: bool, warnings: list[str]) -> tuple[str, str]:
    obj_name = str(op.get("object", ""))
    slot = op.get("slot")
    mat_name = str(op.get("material", ""))
    obj = _object_by_name(obj_name)
    if obj is None:
        return "failed", f"Object '{obj_name}' not found."
    if not isinstance(slot, int):
        return "failed", "'slot' must be an integer index."
    mat = _material_by_name(mat_name)
    if mat is None:
        return "failed", f"Material '{mat_name}' not found."
    if slot < 0 or slot >= len(obj.material_slots):
        return "failed", f"Material slot index {slot} out of range for '{obj_name}'."
    if dry_run:
        return "would_apply", f"Would assign material '{mat_name}' to slot {slot} on '{obj_name}'."
    obj.material_slots[slot].material = mat
    return "applied", f"Set slot {slot} on '{obj_name}' to material '{mat_name}'."


def _op_add_material_slot(op: dict[str, Any], dry_run: bool, warnings: list[str]) -> tuple[str, str]:
    obj_name = str(op.get("object", ""))
    mat_arg = op.get("material")
    obj = _object_by_name(obj_name)
    if obj is None:
        return "failed", f"Object '{obj_name}' not found."
    mats = _mesh_materials(obj)
    if mats is None:
        return "failed", f"Object '{obj_name}' has no material slots."
    mat = _material_by_name(str(mat_arg)) if mat_arg is not None else None
    if mat_arg is not None and mat is None:
        return "failed", f"Material '{mat_arg}' not found."
    if dry_run:
        return "would_apply", f"Would add material slot on '{obj_name}'."
    mats.append(mat)
    return "applied", f"Added material slot on '{obj_name}'."


def _op_remove_material_slot(op: dict[str, Any], dry_run: bool, warnings: list[str]) -> tuple[str, str]:
    obj_name = str(op.get("object", ""))
    slot = op.get("slot")
    obj = _object_by_name(obj_name)
    if obj is None:
        return "failed", f"Object '{obj_name}' not found."
    if not isinstance(slot, int):
        return "failed", "'slot' must be an integer index."
    mats = _mesh_materials(obj)
    if mats is None:
        return "failed", f"Object '{obj_name}' has no material slots."
    if slot < 0 or slot >= len(mats):
        return "failed", f"Material slot index {slot} out of range for '{obj_name}'."
    if dry_run:
        return "would_apply", f"Would remove material slot {slot} from '{obj_name}'."
    # Use mesh data API so objects not in the active view layer still work.
    try:
        mats.pop(index=slot)
    except TypeError:
        mats.pop(slot)
    return "applied", f"Removed material slot {slot} from '{obj_name}'."


def _op_clear_material_slots(op: dict[str, Any], dry_run: bool, warnings: list[str]) -> tuple[str, str]:
    obj_name = str(op.get("object", ""))
    obj = _object_by_name(obj_name)
    if obj is None:
        return "failed", f"Object '{obj_name}' not found."
    mats = _mesh_materials(obj)
    if mats is None:
        return "failed", f"Object '{obj_name}' has no material slots."
    if dry_run:
        return "would_apply", f"Would clear all material slots on '{obj_name}'."
    mats.clear()
    return "applied", f"Cleared material slots on '{obj_name}'."


def _op_set_custom_property(op: dict[str, Any], dry_run: bool, warnings: list[str]) -> tuple[str, str]:
    obj_name = str(op.get("object", ""))
    key = str(op.get("key", ""))
    value = op.get("value")
    obj = _object_by_name(obj_name)
    if obj is None:
        return "failed", f"Object '{obj_name}' not found."
    if not key:
        return "failed", "Missing 'key' for custom property."
    if dry_run:
        return "would_apply", f"Would set custom property '{key}' on '{obj_name}'."
    obj[key] = value
    return "applied", f"Set custom property '{key}' on '{obj_name}'."


def _op_set_scene_property(op: dict[str, Any], dry_run: bool, warnings: list[str]) -> tuple[str, str]:
    path = str(op.get("path", ""))
    value = op.get("value")
    if not path:
        return "failed", "Missing 'path' for scene property."
    if dry_run:
        return "would_apply", f"Would set scene property '{path}'."
    _set_scene_property(path, value)
    return "applied", f"Set scene property '{path}'."


def _dispatch_operation(
    op: dict[str, Any], dry_run: bool, warnings: list[str]
) -> tuple[str, str]:
    op_type = str(op.get("type", ""))
    if op_type == "rename_object":
        return _op_rename_object(op, dry_run, warnings)
    if op_type == "rename_material":
        return _op_rename_material(op, dry_run, warnings)
    if op_type == "join_objects":
        return _op_join_objects(op, dry_run, warnings)
    if op_type == "delete_object":
        return _op_delete_object(op, dry_run, warnings)
    if op_type == "duplicate_object":
        return _op_duplicate_object(op, dry_run, warnings)
    if op_type == "add_modifier":
        return _op_add_modifier(op, dry_run, warnings)
    if op_type == "remove_modifier":
        return _op_remove_modifier(op, dry_run, warnings)
    if op_type == "apply_modifiers":
        return _op_apply_modifiers(op, dry_run, warnings)
    if op_type == "set_material":
        return _op_set_material(op, dry_run, warnings)
    if op_type == "add_material_slot":
        return _op_add_material_slot(op, dry_run, warnings)
    if op_type == "remove_material_slot":
        return _op_remove_material_slot(op, dry_run, warnings)
    if op_type == "clear_material_slots":
        return _op_clear_material_slots(op, dry_run, warnings)
    if op_type == "set_custom_property":
        return _op_set_custom_property(op, dry_run, warnings)
    if op_type == "set_scene_property":
        return _op_set_scene_property(op, dry_run, warnings)
    if op_type == "create_collection":
        return _op_create_collection(op, dry_run, warnings)
    if op_type == "rename_collection":
        return _op_rename_collection(op, dry_run, warnings)
    if op_type == "link_object_to_collection":
        return _op_link_object_to_collection(op, dry_run, warnings)
    if op_type == "unlink_object_from_collection":
        return _op_unlink_object_from_collection(op, dry_run, warnings)
    if op_type == "move_object_to_collection":
        return _op_move_object_to_collection(op, dry_run, warnings)
    if op_type == "create_object":
        return _op_create_object(op, dry_run, warnings)
    return "failed", f"Unknown operation type '{op_type}'."


def main() -> None:
    payload = decode_payload_from_argv()
    operations = payload.get("operations", [])
    if not isinstance(operations, list):
        operations = []
    dry_run = bool(payload.get("dry_run", False))
    output_path = payload.get("output_path")
    output_str = str(output_path) if output_path else None

    warnings: list[str] = []
    errors: list[str] = []
    results: list[dict[str, Any]] = []

    applied = skipped = op_failed = 0

    for index, raw_op in enumerate(operations):
        op_type = "?"
        if not isinstance(raw_op, dict):
            status, detail = "failed", "Operation is not a JSON object."
        else:
            op_type = str(raw_op.get("type", "?"))
            try:
                status, detail = _dispatch_operation(raw_op, dry_run, warnings)
            except Exception as exc:  # noqa: BLE001
                status, detail = "failed", str(exc)

        if status in ("applied", "would_apply"):
            applied += 1
        elif status in ("skipped", "would_skip"):
            skipped += 1
        else:
            op_failed += 1
            errors.append(f"[{index}] {op_type}: {detail}")

        results.append({"index": index, "type": op_type, "status": status, "detail": detail})

    if not dry_run:
        try:
            if output_str:
                bpy.ops.wm.save_as_mainfile(filepath=output_str)
            else:
                bpy.ops.wm.save_mainfile()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"save: {exc}")

    summary = {
        "operations_total": len(operations),
        "operations_applied": applied,
        "operations_skipped": skipped,
        "operations_failed": op_failed,
    }

    dump_json_line(
        {
            "summary": summary,
            "data": {"operation_results": results},
            "warnings": warnings,
            "errors": errors,
        }
    )


if __name__ == "__main__":
    main()
