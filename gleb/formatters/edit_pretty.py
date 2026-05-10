"""Human-friendly terminal formatting for edit output."""

from __future__ import annotations

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from gleb.models.edit_schema import EditResult


def render_edit_pretty(result: EditResult, console: Console | None = None) -> None:
    out = console or Console()
    out.print(f"[bold]File:[/bold] {result.meta.file}")
    out.print(f"[bold]Blender:[/bold] {result.meta.blender_version}")
    out.print(f"[bold]Dry run:[/bold] {result.meta.dry_run}")
    out.print(f"[bold]Operations:[/bold] {result.meta.operations_count}")
    out.print()

    s = result.summary
    out.print(
        f"[bold]Summary:[/bold] {s.operations_applied} applied, "
        f"{s.operations_skipped} skipped, {s.operations_failed} failed "
        f"(total {s.operations_total})"
    )
    out.print()

    table = Table(title="Operation results")
    table.add_column("idx", justify="right")
    table.add_column("type")
    table.add_column("status")
    table.add_column("detail")

    for row in result.data.operation_results:
        status = str(row.status)
        if status in ("applied", "would_apply"):
            status_cell = f"[green]{escape(status)}[/green]"
        elif status in ("skipped", "would_skip"):
            status_cell = f"[yellow]{escape(status)}[/yellow]"
        else:
            status_cell = f"[red]{escape(status)}[/red]"
        table.add_row(str(row.index), escape(row.type), status_cell, escape(row.detail))

    out.print(table)

    if result.warnings:
        out.print()
        out.print("[yellow]Warnings:[/yellow]")
        for warning in result.warnings:
            out.print(f"- {escape(warning)}")

    if result.errors:
        out.print()
        out.print("[red]Errors:[/red]")
        for err in result.errors:
            out.print(f"- {escape(err)}")
