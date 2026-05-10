"""Tests for collection / create_object edit operations (uses repo minimal.blend copy)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MINIMAL_BLEND = ROOT / "tests" / "fixtures" / "minimal.blend"

pytestmark = pytest.mark.skipif(not MINIMAL_BLEND.is_file(), reason=f"Missing fixture: {MINIMAL_BLEND}")


@pytest.fixture()
def minimal_copy(tmp_path: Path) -> Path:
    dest = tmp_path / "minimal.blend"
    shutil.copy(MINIMAL_BLEND, dest)
    return dest


def _env() -> dict[str, str]:
    e = dict(os.environ)
    e.setdefault("BLENDER_PATH", "/usr/bin/blender")
    return e


def _gleb(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gleb", *args],
        cwd=ROOT,
        env=_env(),
        check=False,
        capture_output=True,
        text=True,
    )


def _object_collections(blend: Path, object_name: str) -> set[str]:
    proc = _gleb(["explore", str(blend), "--scope", "objects"])
    assert proc.returncode == 0, proc.stderr
    for obj in json.loads(proc.stdout)["data"]["objects"]:
        if obj["name"] == object_name:
            return set(obj.get("collections", []))
    raise AssertionError(f"Object {object_name!r} not found")


def test_create_rename_collection(minimal_copy: Path) -> None:
    proc = _gleb(
        [
            "edit",
            str(minimal_copy),
            "--op",
            json.dumps({"type": "create_collection", "name": "Gleb_A"}),
            "--op",
            json.dumps({"type": "rename_collection", "from": "Gleb_A", "to": "Gleb_B"}),
        ]
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["summary"]["operations_applied"] == 2

    exp = _gleb(["explore", str(minimal_copy), "--scope", "collections"])
    names = {c["name"] for c in json.loads(exp.stdout)["data"]["structure"]["collections"]}
    assert "Gleb_B" in names
    assert "Gleb_A" not in names


def test_move_object_between_collections(minimal_copy: Path) -> None:
    target = "Gleb_Target"
    create = _gleb(
        [
            "edit",
            str(minimal_copy),
            "--op",
            json.dumps({"type": "create_collection", "name": target}),
        ]
    )
    assert create.returncode == 0, create.stderr

    move = _gleb(
        [
            "edit",
            str(minimal_copy),
            "--op",
            json.dumps(
                {
                    "type": "move_object_to_collection",
                    "object": "Cube",
                    "from_collection": "Collection",
                    "to_collection": target,
                }
            ),
        ]
    )
    assert move.returncode == 0, move.stderr

    cols = _object_collections(minimal_copy, "Cube")
    assert target in cols
    assert "Collection" not in cols


def test_link_and_unlink_object(minimal_copy: Path) -> None:
    # Cube starts only in "Collection"
    extra = "Gleb_Extra"
    p1 = _gleb(
        [
            "edit",
            str(minimal_copy),
            "--op",
            json.dumps({"type": "create_collection", "name": extra}),
        ]
    )
    assert p1.returncode == 0, p1.stderr

    p2 = _gleb(
        [
            "edit",
            str(minimal_copy),
            "--op",
            json.dumps({"type": "link_object_to_collection", "object": "Light", "collection": extra}),
        ]
    )
    assert p2.returncode == 0, p2.stderr
    assert "Collection" in _object_collections(minimal_copy, "Light")
    assert extra in _object_collections(minimal_copy, "Light")

    p3 = _gleb(
        [
            "edit",
            str(minimal_copy),
            "--op",
            json.dumps({"type": "unlink_object_from_collection", "object": "Light", "collection": "Collection"}),
        ]
    )
    assert p3.returncode == 0, p3.stderr
    cols = _object_collections(minimal_copy, "Light")
    assert cols == {extra}


def test_create_object_mesh(minimal_copy: Path) -> None:
    proc = _gleb(
        [
            "edit",
            str(minimal_copy),
            "--op",
            json.dumps(
                {
                    "type": "create_object",
                    "name": "Gleb_NewMesh",
                    "object_type": "MESH",
                    "collection": "Collection",
                }
            ),
        ]
    )
    assert proc.returncode == 0, proc.stderr
    exp = _gleb(["explore", str(minimal_copy), "--scope", "objects"])
    names = {o["name"] for o in json.loads(exp.stdout)["data"]["objects"]}
    assert "Gleb_NewMesh" in names
