from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REAL_BLEND = Path("/home/gleb/Git/concrete/source/9_1_base.blend")


pytestmark = pytest.mark.skipif(not REAL_BLEND.is_file(), reason=f"Missing blend fixture: {REAL_BLEND}")


@pytest.fixture()
def blend_copy(tmp_path: Path) -> Path:
    dest = tmp_path / "test.blend"
    shutil.copy(REAL_BLEND, dest)
    return dest


def _gleb_env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("BLENDER_PATH", "/usr/bin/blender")
    return env


def _run_gleb(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gleb", *args],
        cwd=root,
        env=_gleb_env(),
        check=False,
        capture_output=True,
        text=True,
    )


def _first_mesh_object_name(blend: Path, root: Path) -> str:
    proc = _run_gleb(root, ["explore", str(blend), "--scope", "objects"])
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    for obj in payload["data"]["objects"]:
        if obj.get("type") == "MESH":
            return str(obj["name"])
    pytest.skip("No mesh object in fixture blend")


def _first_material_name(blend: Path, root: Path) -> str:
    proc = _run_gleb(root, ["explore", str(blend), "--scope", "materials"])
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    mats = payload["data"]["materials"]
    assert mats, "No materials in fixture blend"
    return str(mats[0]["name"])


def test_edit_envelope_shape(blend_copy: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    name = _first_mesh_object_name(blend_copy, root)
    op = json.dumps({"type": "rename_object", "from": name, "to": f"{name}_gleb_edit_test"})
    proc = _run_gleb(root, ["edit", str(blend_copy), "--op", op, "--dry-run"])
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    for key in ("meta", "summary", "data", "warnings", "errors"):
        assert key in payload
    assert "operation_results" in payload["data"]
    assert payload["meta"]["command"] == "edit"


def test_edit_dry_run_no_mtime_change(blend_copy: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    name = _first_mesh_object_name(blend_copy, root)
    mtime_before = blend_copy.stat().st_mtime_ns
    op = json.dumps({"type": "rename_object", "from": name, "to": f"{name}_renamed"})
    proc = _run_gleb(root, ["edit", str(blend_copy), "--op", op, "--dry-run"])
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["data"]["operation_results"][0]["status"] == "would_apply"
    assert blend_copy.stat().st_mtime_ns == mtime_before


def test_edit_rename_object(blend_copy: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    old = _first_mesh_object_name(blend_copy, root)
    new = f"{old}_renamed_by_gleb"
    op = json.dumps({"type": "rename_object", "from": old, "to": new})
    proc = _run_gleb(root, ["edit", str(blend_copy), "--op", op])
    assert proc.returncode == 0, proc.stderr

    exp = _run_gleb(root, ["explore", str(blend_copy), "--scope", "objects"])
    assert exp.returncode == 0, exp.stderr
    names = {o["name"] for o in json.loads(exp.stdout)["data"]["objects"]}
    assert new in names
    assert old not in names


def test_edit_rename_object_idempotent(blend_copy: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    name = _first_mesh_object_name(blend_copy, root)
    op = json.dumps({"type": "rename_object", "from": name, "to": name})
    proc = _run_gleb(root, ["edit", str(blend_copy), "--op", op])
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["data"]["operation_results"][0]["status"] == "skipped"


def test_edit_add_modifier(blend_copy: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    mesh_name = _first_mesh_object_name(blend_copy, root)
    op = json.dumps(
        {
            "type": "add_modifier",
            "object": mesh_name,
            "modifier_type": "SUBSURF",
            "name": "GlebSubsurfTest",
            "settings": {"levels": 1},
        }
    )
    proc = _run_gleb(root, ["edit", str(blend_copy), "--op", op])
    assert proc.returncode == 0, proc.stderr

    exp = _run_gleb(root, ["explore", str(blend_copy), "--scope", "modifiers", "--object", mesh_name])
    assert exp.returncode == 0, exp.stderr
    mods = json.loads(exp.stdout)["data"]["modifiers"]
    names = [m["name"] for m in mods if m.get("object") == mesh_name]
    assert "GlebSubsurfTest" in names


def test_edit_add_remove_material_slot(blend_copy: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    mesh_name = _first_mesh_object_name(blend_copy, root)
    mat_name = _first_material_name(blend_copy, root)

    before = _run_gleb(root, ["explore", str(blend_copy), "--scope", "objects", "--object", mesh_name])
    assert before.returncode == 0, before.stderr
    count_before = len(json.loads(before.stdout)["data"]["objects"][0].get("materials", []))

    add_op = json.dumps({"type": "add_material_slot", "object": mesh_name, "material": mat_name})
    proc_add = _run_gleb(root, ["edit", str(blend_copy), "--op", add_op])
    assert proc_add.returncode == 0, proc_add.stderr

    mid = _run_gleb(root, ["explore", str(blend_copy), "--scope", "objects", "--object", mesh_name])
    count_mid = len(json.loads(mid.stdout)["data"]["objects"][0].get("materials", []))
    assert count_mid == count_before + 1

    remove_op = json.dumps({"type": "remove_material_slot", "object": mesh_name, "slot": count_mid - 1})
    proc_rm = _run_gleb(root, ["edit", str(blend_copy), "--op", remove_op])
    assert proc_rm.returncode == 0, proc_rm.stderr

    after = _run_gleb(root, ["explore", str(blend_copy), "--scope", "objects", "--object", mesh_name])
    count_after = len(json.loads(after.stdout)["data"]["objects"][0].get("materials", []))
    assert count_after == count_before


def test_edit_output_does_not_touch_source(blend_copy: Path, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    mesh_name = _first_mesh_object_name(blend_copy, root)
    out_path = tmp_path / "out.blend"
    mtime_before = blend_copy.stat().st_mtime_ns
    op = json.dumps({"type": "add_modifier", "object": mesh_name, "modifier_type": "SOLIDIFY", "name": "GlebSolidifyOut"})
    proc = _run_gleb(
        root,
        ["edit", str(blend_copy), "--output", str(out_path), "--op", op],
    )
    assert proc.returncode == 0, proc.stderr
    assert out_path.is_file()
    assert blend_copy.stat().st_mtime_ns == mtime_before


def test_edit_ops_file(blend_copy: Path, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    mesh = _first_mesh_object_name(blend_copy, root)
    a = f"{mesh}_ops_a"
    b = f"{mesh}_ops_b"
    ops_path = tmp_path / "ops.json"
    ops_path.write_text(
        json.dumps(
            [
                {"type": "rename_object", "from": mesh, "to": a},
                {"type": "rename_object", "from": a, "to": b},
            ]
        ),
        encoding="utf-8",
    )
    proc = _run_gleb(root, ["edit", str(blend_copy), "--ops-file", str(ops_path)])
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["summary"]["operations_applied"] == 2
    assert payload["summary"]["operations_failed"] == 0


def test_edit_partial_failure(blend_copy: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    mesh = _first_mesh_object_name(blend_copy, root)
    new_name = f"{mesh}_partial_ok"
    ops = json.dumps({"type": "rename_object", "from": mesh, "to": new_name})
    bad = json.dumps({"type": "rename_object", "from": "___does_not_exist___", "to": "X"})
    proc = _run_gleb(root, ["edit", str(blend_copy), "--op", ops, "--op", bad])
    assert proc.returncode == 1, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["data"]["operation_results"][0]["status"] == "applied"
    assert payload["data"]["operation_results"][1]["status"] == "failed"
    assert payload["summary"]["operations_failed"] == 1
    assert payload["errors"]
