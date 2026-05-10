"""Utilities for invoking Blender in background mode."""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
from pathlib import Path
from shutil import which
from typing import Any

from gleb.core.exceptions import (
    BlenderExecutionError,
    BlenderNotFoundError,
    BlenderOutputError,
    BlenderVersionError,
)

MIN_BLENDER_MAJOR = 5


def find_blender_path() -> str:
    """Find Blender executable from env or PATH."""
    env_path = os.environ.get("BLENDER_PATH")
    if env_path and Path(env_path).is_file():
        return env_path

    resolved = which("blender")
    if resolved:
        return resolved
    raise BlenderNotFoundError(
        "Blender executable not found. Set BLENDER_PATH or add blender to PATH."
    )


def blender_version(blender_path: str) -> str:
    """Return Blender version string."""
    try:
        proc = subprocess.run(
            [blender_path, "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise BlenderNotFoundError(f"Failed to execute blender at {blender_path}") from exc

    if proc.returncode != 0:
        raise BlenderExecutionError(proc.stderr.strip() or "Failed to query Blender version.")

    line = proc.stdout.splitlines()[0] if proc.stdout else ""
    match = re.search(r"Blender\s+([0-9]+\.[0-9]+(?:\.[0-9]+)?)", line)
    if not match:
        raise BlenderOutputError(f"Could not parse Blender version from: {line!r}")
    return match.group(1)


def ensure_supported_blender(blender_path: str) -> str:
    """Validate Blender major version support."""
    version = blender_version(blender_path)
    major = int(version.split(".", maxsplit=1)[0])
    if major < MIN_BLENDER_MAJOR:
        raise BlenderVersionError(
            f"Unsupported Blender version {version}. Blender {MIN_BLENDER_MAJOR}+ is required."
        )
    return version


def _extract_last_json(stdout: str) -> dict[str, Any]:
    """Extract the final JSON object from stdout."""
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise BlenderOutputError("No JSON object found in Blender output.")


def _run_blender_cmd(
    cmd: list[str],
    quiet: bool = False,
) -> str:
    """Execute a Blender command and return stdout."""
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL if quiet else subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        raise BlenderExecutionError(f"Failed to execute Blender command: {' '.join(cmd)}") from exc

    if proc.returncode != 0:
        stderr = proc.stderr.strip() if proc.stderr else "Unknown Blender error."
        raise BlenderExecutionError(stderr)

    return proc.stdout or ""


def run_blender_probe(
    blend_file: Path,
    probe_script: Path,
    payload: dict[str, Any],
    blender_path: str | None = None,
    quiet: bool = False,
) -> tuple[dict[str, Any], str]:
    """Run Blender with a probe script against an existing .blend file."""
    resolved_blender = blender_path or find_blender_path()
    version = ensure_supported_blender(resolved_blender)

    encoded_payload = base64.b64encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).decode("ascii")

    cmd = [
        resolved_blender,
        "-b",
        str(blend_file),
        "--python",
        str(probe_script),
        "--",
        encoded_payload,
    ]

    stdout = _run_blender_cmd(cmd, quiet=quiet)
    parsed = _extract_last_json(stdout)
    return parsed, version


def run_blender_script(
    probe_script: Path,
    payload: dict[str, Any],
    blender_path: str | None = None,
    quiet: bool = False,
) -> tuple[dict[str, Any], str]:
    """Run Blender without an existing blend file (opens an empty default scene)."""
    resolved_blender = blender_path or find_blender_path()
    version = ensure_supported_blender(resolved_blender)

    encoded_payload = base64.b64encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).decode("ascii")

    cmd = [
        resolved_blender,
        "-b",
        "--python",
        str(probe_script),
        "--",
        encoded_payload,
    ]

    stdout = _run_blender_cmd(cmd, quiet=quiet)
    parsed = _extract_last_json(stdout)
    return parsed, version
