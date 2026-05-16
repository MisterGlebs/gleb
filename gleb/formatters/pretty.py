"""Human-friendly terminal formatting for explore output."""

from __future__ import annotations

from collections import defaultdict

from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.tree import Tree

from gleb.core.json_diff import LEAF, ONLY_LEFT, ONLY_RIGHT
from gleb.models.compare_schema import CompareResult
from gleb.models.explore_schema import ExploreResult
from gleb.models.glb_schema import GlbCompareResult, GlbInspectResult


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


def _walk_compare_diff(parent: Tree, node: object, label: str) -> None:
    if isinstance(node, dict):
        if LEAF in node:
            leaf = node[LEAF]
            lv = leaf.get("left")
            rv = leaf.get("right")
            parent.add(f"{escape(label)}: [red]{lv!r}[/red] → [green]{rv!r}[/green]")
            return
        if ONLY_LEFT in node:
            parent.add(f"{escape(label)}: [yellow]−[/yellow] {node[ONLY_LEFT]!r} [dim](left only)[/dim]")
            return
        if ONLY_RIGHT in node:
            parent.add(f"{escape(label)}: [green]+[/green] {node[ONLY_RIGHT]!r} [dim](right only)[/dim]")
            return
        branch = parent.add(escape(label))
        for key in sorted(node.keys()):
            _walk_compare_diff(branch, node[key], str(key))
        return
    parent.add(f"{escape(label)}: {node!r}")


def render_compare_pretty(result: CompareResult, console: Console | None = None) -> None:
    out = console or Console()
    m = result.meta
    out.print(f"[bold]Left:[/bold] {m.left_file}")
    out.print(f"[bold]Right:[/bold] {m.right_file}")
    out.print(f"[bold]Blender:[/bold] {m.left_blender_version} vs {m.right_blender_version}")
    out.print(f"[bold]Scope:[/bold] {m.scope}")
    out.print(f"[bold]Identical:[/bold] {'yes' if m.identical else 'no'}")
    out.print(f"[bold]Changed paths:[/bold] {result.summary.changed_paths}")
    out.print()

    ch = result.data.changes
    if ch.summary:
        out.print("[bold]Summary diff[/bold]")
        tree = Tree("summary")
        for key in sorted(ch.summary.keys()):
            _walk_compare_diff(tree, ch.summary[key], str(key))
        out.print(tree)
        out.print()

    if ch.explore_data:
        out.print("[bold]Data diff[/bold]")
        tree_d = Tree("explore_data")
        for key in sorted(ch.explore_data.keys()):
            _walk_compare_diff(tree_d, ch.explore_data[key], str(key))
        out.print(tree_d)
        out.print()

    if result.summary.paths:
        path_table = Table(title="Paths (sample)", show_lines=False)
        path_table.add_column("path", overflow="fold")
        max_rows = 200
        for p in result.summary.paths[:max_rows]:
            path_table.add_row(p)
        if len(result.summary.paths) > max_rows:
            path_table.add_row(f"[dim]… {len(result.summary.paths) - max_rows} more[/dim]")
        out.print(path_table)

    if result.warnings:
        out.print("[yellow]Warnings:[/yellow]")
        for warning in result.warnings:
            out.print(f"- {warning}")


# ---------------------------------------------------------------------------
# glb pretty renderers
# ---------------------------------------------------------------------------


def render_glb_pretty(result: GlbInspectResult, console: Console | None = None) -> None:
    out = console or Console()
    out.print(f"[bold]Blender:[/bold] {result.meta.blender_version}")
    out.print(
        f"[bold]Files:[/bold] {result.summary.files_inspected} "
        f"(failed: {result.summary.files_failed})  "
        f"[bold]Objects:[/bold] {result.summary.objects_total}"
    )
    out.print()

    for inspect in result.data.inspects:
        head = f"[bold]{inspect.path}[/bold]"
        if inspect.import_failed:
            out.print(f"{head}  [red]IMPORT FAILED[/red]")
            continue
        out.print(f"{head}  objects={len(inspect.objects)}")
        table = Table(show_lines=False, box=None)
        table.add_column("name", overflow="fold")
        table.add_column("type", style="dim")
        table.add_column("parent", overflow="fold", style="dim")
        table.add_column("verts", justify="right")
        table.add_column("polys", justify="right")
        table.add_column("uv", justify="right")
        table.add_column("slots", overflow="fold")
        table.add_column("polys/slot", overflow="fold", style="dim")
        for o in inspect.objects:
            slot_names = [
                (s.material.name if s.material else "<empty>") for s in o.material_slots
            ]
            polys_per = ", ".join(f"{k}:{v}" for k, v in sorted(o.polys_per_slot.items()))
            table.add_row(
                escape(o.name),
                o.type,
                escape(o.parent or ""),
                str(o.vertices),
                str(o.polygons),
                str(o.uv_layers),
                escape(", ".join(slot_names)),
                polys_per,
            )
        out.print(table)
        out.print()

    if result.warnings:
        out.print("[yellow]Warnings:[/yellow]")
        for w in result.warnings:
            out.print(f"- {w}")
    if result.errors:
        out.print("[red]Errors:[/red]")
        for e in result.errors:
            out.print(f"- {e}")


def render_glb_compare_pretty(result: GlbCompareResult, console: Console | None = None) -> None:
    out = console or Console()
    out.print(f"[bold]Left:[/bold] {result.meta.left}")
    out.print(f"[bold]Right:[/bold] {result.meta.right}")
    out.print(f"[bold]Blender:[/bold] {result.meta.blender_version}")
    out.print(
        f"[bold]Pairs:[/bold] {result.summary.pairs}  "
        f"identical={result.summary.pairs_identical}  "
        f"changed={result.summary.pairs_changed}"
    )
    out.print(f"[bold]Identical:[/bold] {'yes' if result.meta.identical else 'no'}")
    if result.summary.pairs_only_in_left:
        out.print(f"[yellow]Only in left:[/yellow] {result.summary.pairs_only_in_left}")
    if result.summary.pairs_only_in_right:
        out.print(f"[yellow]Only in right:[/yellow] {result.summary.pairs_only_in_right}")
    out.print()

    for pair in result.data.pairs:
        marker = "[green]identical[/green]" if pair.identical else "[red]changed[/red]"
        out.print(
            f"[bold]{pair.name}[/bold]  {marker}  "
            f"objects {pair.object_count_left}→{pair.object_count_right}"
        )
        if pair.objects_only_in_left:
            sample = pair.objects_only_in_left[:10]
            more = "" if len(pair.objects_only_in_left) <= 10 else f" (+{len(pair.objects_only_in_left)-10} more)"
            out.print(f"  [yellow]missing in right:[/yellow] {sample}{more}")
        if pair.objects_only_in_right:
            sample = pair.objects_only_in_right[:10]
            more = "" if len(pair.objects_only_in_right) <= 10 else f" (+{len(pair.objects_only_in_right)-10} more)"
            out.print(f"  [yellow]extra in right:[/yellow] {sample}{more}")
        if pair.object_diffs:
            t = Table(show_lines=False, box=None)
            t.add_column("object", overflow="fold")
            t.add_column("fields_changed", overflow="fold")
            for d in pair.object_diffs[:30]:
                t.add_row(escape(d.name), escape(", ".join(d.fields_changed)))
            if len(pair.object_diffs) > 30:
                t.add_row("[dim]…[/dim]", f"[dim]+{len(pair.object_diffs)-30} more[/dim]")
            out.print(t)
        out.print()

    if result.warnings:
        out.print("[yellow]Warnings:[/yellow]")
        for w in result.warnings:
            out.print(f"- {w}")
    if result.errors:
        out.print("[red]Errors:[/red]")
        for e in result.errors:
            out.print(f"- {e}")
