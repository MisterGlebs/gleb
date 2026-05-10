from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def test_explore_outputs_json_for_fixture() -> None:
    root = Path(__file__).resolve().parents[1]
    blend = root / "tests" / "fixtures" / "minimal.blend"
    env = dict(os.environ)
    env.setdefault("BLENDER_PATH", "/usr/bin/blender")

    proc = subprocess.run(
        ["gleb", "explore", str(blend), "--scope", "scene"],
        cwd=root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert "meta" in payload
    assert "summary" in payload
    assert "data" in payload
    assert "structure" in payload["data"]
    assert "collections" in payload["data"]["structure"]
    assert "relations" in payload["data"]["structure"]
    assert payload["meta"]["scope"] == "scene"


def test_explore_constraints_and_detail_output() -> None:
    root = Path(__file__).resolve().parents[1]
    blend = root / "tests" / "fixtures" / "minimal.blend"
    env = dict(os.environ)
    env.setdefault("BLENDER_PATH", "/usr/bin/blender")

    constraints_proc = subprocess.run(
        ["gleb", "explore", str(blend), "--scope", "constraints"],
        cwd=root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert constraints_proc.returncode == 0, constraints_proc.stderr
    constraints_payload = json.loads(constraints_proc.stdout)
    assert constraints_payload["meta"]["scope"] == "constraints"
    assert "constraints" in constraints_payload["data"]
    assert isinstance(constraints_payload["data"]["constraints"], list)

    detail_proc = subprocess.run(
        ["gleb", "explore", str(blend), "--scope", "objects", "--detail"],
        cwd=root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert detail_proc.returncode == 0, detail_proc.stderr
    detail_payload = json.loads(detail_proc.stdout)
    assert detail_payload["meta"]["scope"] == "objects"
    assert detail_payload["data"]["objects"]
    first_object = detail_payload["data"]["objects"][0]
    assert "transforms" in first_object
    assert "constraints" in first_object


def test_explore_new_scopes_and_diagnose() -> None:
    root = Path(__file__).resolve().parents[1]
    blend = root / "tests" / "fixtures" / "minimal.blend"
    env = dict(os.environ)
    env.setdefault("BLENDER_PATH", "/usr/bin/blender")

    for scope, key in [
        ("geometry", "geometry"),
        ("textures", "textures"),
        ("armatures", "armatures"),
        ("libraries", "libraries"),
        ("custom_properties", "custom_properties"),
    ]:
        proc = subprocess.run(
            ["gleb", "explore", str(blend), "--scope", scope],
            cwd=root,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["meta"]["scope"] == scope
        assert key in payload["data"]
        assert isinstance(payload["data"][key], list)

    diagnose_proc = subprocess.run(
        ["gleb", "explore", str(blend), "--scope", "all", "--detail", "--diagnose"],
        cwd=root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert diagnose_proc.returncode == 0, diagnose_proc.stderr
    diagnose_payload = json.loads(diagnose_proc.stdout)
    assert "diagnostics" in diagnose_payload["data"]
    assert "diagnostics" in diagnose_payload["summary"]
    assert isinstance(diagnose_payload["data"]["diagnostics"], list)
    if diagnose_payload["data"]["diagnostics"]:
        first_code = diagnose_payload["data"]["diagnostics"][0]["code"]
        assert isinstance(first_code, str)
