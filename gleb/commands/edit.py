"""CLI command: edit."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from gleb.commands.edit_utils import run_edit
from gleb.core.exceptions import BlenderNotFoundError, BlenderVersionError, GlebError
from gleb.formatters.edit_pretty import render_edit_pretty


def edit_command(
    blend_file: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        help="Path to the .blend file to modify. Saved in place unless --output is set.",
    ),
    op: list[str] | None = typer.Option(
        None,
        "--op",
        help=(
            'A single operation as a JSON object, e.g. \'{"type":"rename_object","from":"Cube","to":"Body"}\'. '
            "Repeatable; combined with any --ops-file operations in order. "
            "Supported types: rename_object, rename_material, join_objects, delete_object, "
            "duplicate_object, create_object, create_collection, rename_collection, "
            "link_object_to_collection, unlink_object_from_collection, move_object_to_collection, "
            "add_modifier, remove_modifier, apply_modifiers, set_material, add_material_slot, "
            "remove_material_slot, clear_material_slots, set_custom_property, set_scene_property."
        ),
    ),
    ops_file: list[Path] | None = typer.Option(
        None,
        "--ops-file",
        exists=True,
        dir_okay=False,
        help=(
            "Path to a JSON file containing an array of operation objects. "
            "Repeatable; operations from multiple files are concatenated in order with --op operations."
        ),
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="Write the modified .blend to this path and leave the source file unchanged. Omit to overwrite source.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Validate and plan all operations without writing anything. Reports what would change.",
    ),
    pretty: bool = typer.Option(
        False,
        "--pretty",
        help="Render a human-readable Rich terminal view instead of emitting JSON. Use JSON mode (default) when piping to agents or other tools.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        help="Suppress Blender's own stderr output. The JSON result envelope is always written to stdout.",
    ),
    blender: str | None = typer.Option(
        None,
        "--blender",
        help="Path to the Blender 5+ executable. Overrides the BLENDER_PATH env var and PATH lookup.",
    ),
) -> None:
    """Apply one or more structured operations to a .blend file and save.

    Operations are JSON objects passed via --op or read from a JSON array file via --ops-file.
    They run in declaration order; failures do not roll back earlier successes.
    Output envelope reports per-operation status with fields: index, type, status, detail.
    Exit code 1 if any operation fails; exit code 2 for bad arguments; exit code 3 if Blender is missing.
    """
    operations: list[dict] = []
    try:
        if op:
            for raw in op:
                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    raise ValueError("Each --op value must be a JSON object.")
                operations.append(parsed)
        if ops_file:
            for path in ops_file:
                text = path.read_text(encoding="utf-8")
                data = json.loads(text)
                if not isinstance(data, list):
                    raise ValueError(f"Ops file {path} must contain a JSON array.")
                for item in data:
                    if not isinstance(item, dict):
                        raise ValueError(f"Each operation in {path} must be a JSON object.")
                    operations.append(item)
        if not operations:
            raise ValueError("Provide at least one operation via --op or --ops-file.")

        result = run_edit(
            blend_file=blend_file,
            operations=operations,
            dry_run=dry_run,
            output=output,
            blender_path=blender,
            quiet=quiet,
        )
    except (ValueError, json.JSONDecodeError) as exc:
        typer.echo(
            json.dumps(
                {
                    "meta": {
                        "file": str(blend_file),
                        "command": "edit",
                        "dry_run": dry_run,
                        "operations_count": 0,
                    },
                    "summary": {},
                    "data": {},
                    "warnings": [],
                    "errors": [str(exc)],
                },
                ensure_ascii=True,
            )
        )
        raise typer.Exit(code=2) from exc
    except (BlenderNotFoundError, BlenderVersionError) as exc:
        typer.echo(
            json.dumps(
                {
                    "meta": {
                        "file": str(blend_file),
                        "command": "edit",
                        "dry_run": dry_run,
                        "operations_count": len(operations) if operations else 0,
                    },
                    "summary": {},
                    "data": {},
                    "warnings": [],
                    "errors": [str(exc)],
                },
                ensure_ascii=True,
            )
        )
        raise typer.Exit(code=3) from exc
    except GlebError as exc:
        typer.echo(
            json.dumps(
                {
                    "meta": {
                        "file": str(blend_file),
                        "command": "edit",
                        "dry_run": dry_run,
                        "operations_count": len(operations) if operations else 0,
                    },
                    "summary": {},
                    "data": {},
                    "warnings": [],
                    "errors": [str(exc)],
                },
                ensure_ascii=True,
            )
        )
        raise typer.Exit(code=1) from exc

    if pretty:
        render_edit_pretty(result)
    else:
        typer.echo(result.model_dump_json())

    if result.summary.operations_failed > 0 or result.errors:
        raise typer.Exit(code=1)
