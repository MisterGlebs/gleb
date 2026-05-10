"""Human-readable terminal output for `gleb textures` commands."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from gleb.models.textures_schema import TexturesOrmResult, TexturesProcessResult


def render_textures_process_pretty(result: TexturesProcessResult, console: Console | None = None) -> None:
    out = console or Console()
    out.print(Rule("[bold cyan]gleb textures process[/bold cyan]", style="cyan"))
    out.print(f"[dim]path[/dim] {result.meta.path}")
    summary_bits = (
        f"[bold]{result.summary.sets_total}[/bold] set(s)"
        f" · [yellow]{result.summary.sets_skipped}[/yellow] skipped"
    )
    out.print(summary_bits)
    if result.data.sets:
        table = Table(show_header=True, header_style="bold")
        table.add_column("Set")
        table.add_column("Outcome")
        for row in result.data.sets:
            table.add_row(row.name, row.outcome)
        out.print(table)
    if result.data.messages:
        body = "\n".join(result.data.messages)
        out.print(
            Panel(
                body,
                title="[bold]Pipeline log[/bold]",
                subtitle=f"{len(result.data.messages)} lines",
                border_style="dim",
                padding=(1, 2),
            )
        )
    if result.warnings:
        out.print("[yellow]Warnings[/yellow]")
        for w in result.warnings:
            out.print(f"  • {w}")
    if result.errors:
        out.print("[red]Errors[/red]")
        for e in result.errors:
            out.print(f"  • {e}")
    if not result.errors:
        out.print("[green]Finished[/green]")


def render_textures_orm_pretty(result: TexturesOrmResult, console: Console | None = None) -> None:
    out = console or Console()
    out.print(Rule("[bold cyan]gleb textures orm[/bold cyan]", style="cyan"))
    out.print(f"[dim]output[/dim] [bold]{result.data.output_path}[/bold]")
    out.print(f"[dim]size[/dim] {result.summary.width}×{result.summary.height}")
    ch = []
    if result.meta.ao:
        ch.append(f"AO [dim]{result.meta.ao}[/dim]")
    if result.meta.roughness:
        ch.append(f"Roughness [dim]{result.meta.roughness}[/dim]")
    if result.meta.metallic:
        ch.append(f"Metallic [dim]{result.meta.metallic}[/dim]")
    if ch:
        out.print(" · ".join(ch))
    if result.data.messages:
        out.print(
            Panel(
                "\n".join(result.data.messages),
                title="[bold]Build log[/bold]",
                border_style="dim",
                padding=(1, 2),
            )
        )
    if result.warnings:
        out.print("[yellow]Warnings[/yellow]")
        for w in result.warnings:
            out.print(f"  • {w}")
    if result.errors:
        out.print("[red]Errors[/red]")
        for e in result.errors:
            out.print(f"  • {e}")
    else:
        out.print("[green]Finished[/green]")
