"""CLI: gleb textures — host-side Godot texture pipeline."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from gleb.commands.textures_utils import (
    ensure_texture_dependencies,
    run_textures_orm,
    run_textures_process,
)
from gleb.core.exceptions import GlebError
from gleb.formatters.textures_pretty import render_textures_orm_pretty, render_textures_process_pretty

textures_app = typer.Typer(
    help=(
        "Host-side texture pipeline: ORM packing, Megascans decals, mip folders, Godot .import stubs. "
        "Optional deps: pip install 'gleb[textures]'. "
        "Interactive terminals: Rich report + stderr progress; scripts/pipes: use --json."
    )
)


def _stderr_progress_emitter(*, quiet: bool):
    """Return a callable for phase lines on stderr, or None when suppressed."""

    if quiet:
        return None

    def emit(message: str) -> None:
        if sys.stderr.isatty():
            print(f"[gleb textures] {message}", file=sys.stderr)

    return emit


def _use_stdout_json(*, json_opt: bool, pretty_opt: bool) -> bool:
    """True → print JSON envelope; False → Rich pretty (TTY-aware default)."""
    if json_opt:
        return True
    if pretty_opt:
        return False
    return not sys.stdout.isatty()


@textures_app.callback()
def _textures_root() -> None:
    """Godot texture helpers (runs on the host, not in Blender)."""


@textures_app.command("process")
def textures_process_command(
    path: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=False,
        help="Texture set directory, or a parent directory containing one subdirectory per set.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Emit JSON envelope (agents, pipes). Default when stdout is not a terminal.",
    ),
    pretty: bool = typer.Option(
        False,
        "--pretty",
        "-p",
        help="Force Rich output even when stdout is not a terminal.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress phase lines on stderr (JSON unchanged).",
    ),
) -> None:
    """Run ORM/decal creation, downscale into orig/half/quarter/eighth, write Godot ORM import stubs."""
    use_json = _use_stdout_json(json_opt=json_output, pretty_opt=pretty)
    progress = None if use_json else _stderr_progress_emitter(quiet=quiet)
    try:
        ensure_texture_dependencies()
        result = run_textures_process(path, progress=progress)
    except FileNotFoundError as exc:
        typer.echo(
            json.dumps(
                {
                    "meta": {"runtime": "host", "command": "textures.process", "path": str(path)},
                    "summary": {},
                    "data": {},
                    "warnings": [],
                    "errors": [str(exc)],
                },
                ensure_ascii=True,
            )
        )
        raise typer.Exit(code=1) from exc
    except (ImportError, GlebError, ValueError, OSError) as exc:
        typer.echo(
            json.dumps(
                {
                    "meta": {"runtime": "host", "command": "textures.process", "path": str(path)},
                    "summary": {},
                    "data": {},
                    "warnings": [],
                    "errors": [str(exc)],
                },
                ensure_ascii=True,
            )
        )
        raise typer.Exit(code=1) from exc

    if use_json:
        typer.echo(result.model_dump_json())
        return

    render_textures_process_pretty(result)


@textures_app.command("orm")
def textures_orm_command(
    output: Path = typer.Option(
        ...,
        "--output",
        "-o",
        help="Output ORM PNG path (Godot channel order R=AO, G=roughness, B=metallic).",
    ),
    ao: Path | None = typer.Option(
        None,
        "--ao",
        help="Ambient occlusion map (grayscale image).",
        exists=True,
        dir_okay=False,
    ),
    roughness: Path | None = typer.Option(
        None,
        "--roughness",
        help="Roughness map (grayscale).",
        exists=True,
        dir_okay=False,
    ),
    metallic: Path | None = typer.Option(
        None,
        "--metallic",
        help="Metallic map (grayscale).",
        exists=True,
        dir_okay=False,
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Emit JSON envelope. Default when stdout is not a terminal.",
    ),
    pretty: bool = typer.Option(
        False,
        "--pretty",
        "-p",
        help="Force Rich output even when stdout is not a terminal.",
    ),
) -> None:
    """Pack explicit AO / roughness / metallic files into one ORM PNG."""
    use_json = _use_stdout_json(json_opt=json_output, pretty_opt=pretty)
    if not any([ao, roughness, metallic]):
        err = {
            "meta": {"runtime": "host", "command": "textures.orm", "output": str(output)},
            "summary": {},
            "data": {},
            "warnings": [],
            "errors": ["Provide at least one of --ao, --roughness, --metallic."],
        }
        typer.echo(json.dumps(err, ensure_ascii=True))
        raise typer.Exit(code=2)

    try:
        ensure_texture_dependencies()
        result = run_textures_orm(output=output, ao=ao, roughness=roughness, metallic=metallic)
    except (ImportError, GlebError, ValueError, OSError, FileNotFoundError) as exc:
        typer.echo(
            json.dumps(
                {
                    "meta": {"runtime": "host", "command": "textures.orm", "output": str(output)},
                    "summary": {},
                    "data": {},
                    "warnings": [],
                    "errors": [str(exc)],
                },
                ensure_ascii=True,
            )
        )
        raise typer.Exit(code=1) from exc

    if use_json:
        typer.echo(result.model_dump_json())
        return

    render_textures_orm_pretty(result)
