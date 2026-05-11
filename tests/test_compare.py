from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def test_compare_identical_fixture_exits_zero() -> None:
    root = Path(__file__).resolve().parents[1]
    blend = root / "tests" / "fixtures" / "minimal.blend"
    env = dict(os.environ)
    env.setdefault("BLENDER_PATH", "/usr/bin/blender")

    proc = subprocess.run(
        ["gleb", "compare", str(blend), str(blend), "--scope", "scene"],
        cwd=root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["meta"]["identical"] is True
    assert payload["summary"]["changed_paths"] == 0
    assert payload["data"]["changes"]["summary"] is None
    assert payload["data"]["changes"]["explore_data"] is None


def test_compare_json_structure() -> None:
    """Envelope matches gleb compare schema keys."""
    root = Path(__file__).resolve().parents[1]
    blend = root / "tests" / "fixtures" / "minimal.blend"
    env = dict(os.environ)
    env.setdefault("BLENDER_PATH", "/usr/bin/blender")

    proc = subprocess.run(
        ["gleb", "compare", str(blend), str(blend), "--scope", "objects"],
        cwd=root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    for key in ("meta", "summary", "data", "warnings", "errors"):
        assert key in payload
    assert "changes" in payload["data"]
    assert "left_file" in payload["meta"] and "right_file" in payload["meta"]
