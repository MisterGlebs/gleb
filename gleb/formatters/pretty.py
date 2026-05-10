"""Human-friendly terminal formatting for explore output."""

from __future__ import annotations

from collections import defaultdict

from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.tree import Tree

from gleb.models.explore_schema import ExploreResult


def _build_relations_map(relations: list[dict]) -> dict[str, str | None]:
    parent_by_object: dict[str, str | None] = {}
    for relation in relations:
        object_name = str(relation.get("object", ""))
        if not object_name:
            continue
        parent = relation.get("parent")
        parent_by_object[object_name] = str(parent) if parent else None
    return parent_by_object


def _render_collection_tree(result: ExploreResult, out: Console) -> None:
    collections = result.data.structure.collections
    if not collections:
        return

    children_by_collection: dict[str, list[str]] = {}
    referenced_children: set[str] = set()
    for item in collections:
        name = str(item.get("name", ""))
        if not name:
            continue
        children = [str(child) for child in (item.get("child_collections", []) or [])]
        children_by_collection[name] = children
        referenced_children.update(children)

    root_collections = sorted(
        [name for name in children_by_collection if name not in referenced_children]
    )
    if not root_collections:
        root_collections = sorted(children_by_collection.keys())

    objects_by_collection: dict[str, list[str]] = defaultdict(list)
    object_by_name: dict[str, dict] = {}
    for obj in result.data.objects:
        obj_name = str(obj.get("name", ""))
        if not obj_name:
            continue
        object_by_name[obj_name] = obj
        for coll_name in obj.get("collections", []) or []:
            objects_by_collection[str(coll_name)].append(obj_name)

    for coll_name in objects_by_collection:
        objects_by_collection[coll_name].sort()

    parent_by_object = _build_relations_map(result.data.structure.relations)
    tree = Tree("collections/")
    visited: set[str] = set()

    def add_collection_node(parent: Tree, collection_name: str) -> None:
        if collection_name in visited:
            parent.add(f"{escape(collection_name)}/ [dim](already shown)[/dim]")
            return
        visited.add(collection_name)

        node = parent.add(f"{escape(collection_name)}/")
        for object_name in objects_by_collection.get(collection_name, []):
            parent_name = parent_by_object.get(object_name)
            if parent_name:
                object_node = node.add(
                    f"{escape(object_name)} [dim](parent: {escape(parent_name)})[/dim]"
                )
            else:
                object_node = node.add(escape(object_name))

            obj = object_by_name.get(object_name, {})
            transforms = obj.get("transforms")
            if isinstance(transforms, dict):
                object_node.add(
                    "[dim]transform[/dim] "
                    f"loc={transforms.get('location')} "
                    f"rot={transforms.get('rotation_euler')} "
                    f"scale={transforms.get('scale')}"
                )
            constraint_names = obj.get("constraints")
            if isinstance(constraint_names, list) and constraint_names:
                object_node.add(f"[dim]constraints[/dim] {', '.join(str(v) for v in constraint_names)}")

        for child_name in sorted(children_by_collection.get(collection_name, [])):
            add_collection_node(node, child_name)

    for root_name in root_collections:
        add_collection_node(tree, root_name)

    out.print()
    out.print("[bold]Structure Tree[/bold]")
    out.print(tree)


def render_explore_pretty(result: ExploreResult, console: Console | None = None) -> None:
    out = console or Console()
    out.print(f"[bold]File:[/bold] {result.meta.file}")
    out.print(f"[bold]Blender:[/bold] {result.meta.blender_version}")
    out.print(f"[bold]Scope:[/bold] {result.meta.scope}")
    out.print()

    summary = Table(title="Summary")
    summary.add_column("collections")
    summary.add_column("relations")
    summary.add_column("objects")
    summary.add_column("materials")
    summary.add_column("animations")
    summary.add_column("constraints")
    summary.add_column("geometry")
    summary.add_column("textures")
    summary.add_column("armatures")
    summary.add_column("libraries")
    summary.add_column("custom_props")
    summary.add_column("diagnostics")
    summary.add_row(
        str(result.summary.collections),
        str(result.summary.relations),
        str(result.summary.objects),
        str(result.summary.materials),
        str(result.summary.animations),
        str(result.summary.constraints),
        str(result.summary.geometry),
        str(result.summary.textures),
        str(result.summary.armatures),
        str(result.summary.libraries),
        str(result.summary.custom_properties),
        str(result.summary.diagnostics),
    )
    out.print(summary)
    _render_collection_tree(result, out)

    if result.data.diagnostics:
        grouped: dict[str, list[dict]] = {"error": [], "warning": [], "info": []}
        for item in result.data.diagnostics:
            sev = str(item.get("severity", "info"))
            grouped.setdefault(sev, []).append(item)

        out.print()
        out.print("[bold]Diagnostics[/bold]")
        for severity in ("error", "warning", "info"):
            entries = grouped.get(severity, [])
            if not entries:
                continue
            out.print(f"[bold]{severity.upper()} ({len(entries)})[/bold]")
            for item in entries:
                obj = item.get("object")
                code = item.get("code")
                message = item.get("message")
                if obj:
                    out.print(f"- [{code}] {obj}: {message}")
                else:
                    out.print(f"- [{code}] {message}")

    if result.warnings:
        out.print()
        out.print("[yellow]Warnings:[/yellow]")
        for warning in result.warnings:
            out.print(f"- {warning}")
