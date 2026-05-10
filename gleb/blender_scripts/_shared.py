"""Shared utilities for Blender probe scripts."""

from __future__ import annotations

import base64
import json
import sys
from typing import Any


def decode_payload_from_argv() -> dict[str, Any]:
    """Decode base64 JSON payload passed after `--`."""
    argv = sys.argv
    if "--" not in argv:
        return {}
    idx = argv.index("--")
    if idx + 1 >= len(argv):
        return {}
    encoded = argv[idx + 1]
    raw = base64.b64decode(encoded.encode("ascii")).decode("utf-8")
    value = json.loads(raw)
    if isinstance(value, dict):
        return value
    return {}


def dump_json_line(payload: dict[str, Any]) -> None:
    """Print exactly one JSON object line for the caller."""
    print(json.dumps(payload, separators=(",", ":"), ensure_ascii=True))
