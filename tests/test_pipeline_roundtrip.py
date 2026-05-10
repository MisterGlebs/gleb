"""End-to-end pipeline test: create blend → populate → export glb → import → verify."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from gleb.core.blender_runner import run_blender_probe, run_blender_script

ROOT = Path(__file__).resolve().parents[1]
SETUP_PROBE = ROOT / "gleb" / "blender_scripts" / "roundtrip_setup_probe.py"
IMPORT_PROBE = ROOT / "gleb" / "blender_scripts" / "gltf_import_inspect_probe.py"


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


@pytest.mark.skipif(not shutil.which("gleb"), reason="gleb CLI not on PATH")
@pytest.mark.skipif(
    not Path(os.environ.get("BLENDER_PATH", "/usr/bin/blender")).is_file(),
    reason="Blender executable missing",
)
def test_pipeline_create_edit_export_import_roundtrip(tmp_path: Path) -> None:
    """1. create pipeline blend 2. add meshes+modifiers 3. _support object 4. export 5. import 6. compare."""
    blend = tmp_path / "roundtrip.blend"
    export_dir = tmp_path / "export"

    # 1) Create structure like pipeline_showcase (single asset for simpler export)
    p_create = _gleb(
        [
            "create",
            str(blend),
            "--asset",
            "fac_a",
            "--quiet",
        ]
    )
    assert p_create.returncode == 0, p_create.stdout + p_create.stderr
    cr = json.loads(p_create.stdout)
    assert cr["summary"]["assets_created"] == 1
    assert "fac_a/visual_fac_a/mesh_fac_a/layer_1_fac_a" in cr["data"]["collections"]

    # 2–4) Visual mesh + Subdivision; mesh only under _support (must not appear in asset glb)
    payload = {
        "blend_path": str(blend.resolve()),
        "assets": ["fac_a"],
        "visual_object_prefix": "Vis",
        "support_object_name": "SupportCube",
        "subsurf_levels": 2,
    }
    setup_result, _blender_v = run_blender_probe(blend, SETUP_PROBE, payload, blender_path=_env()["BLENDER_PATH"])
    assert setup_result.get("errors") == [], setup_result
    assert "Vis_fac_a" in setup_result["data"]["objects"]
    assert "SupportCube" in setup_result["data"]["objects"]

    # 5) Export one glb (fac_b absent — only fac_a)
    p_exp = _gleb(
        [
            "export",
            str(blend),
            "--output-dir",
            str(export_dir),
            "--asset",
            "fac_a",
            "--quiet",
        ]
    )
    assert p_exp.returncode == 0, p_exp.stdout + p_exp.stderr

    glb = export_dir / "fac_a.glb"
    assert glb.is_file(), f"missing {glb}"

    # 6) Fresh Blender session: import glb and inspect
    imp_payload = {"glb_paths": [str(glb.resolve())]}
    imp_result, _ = run_blender_script(
        IMPORT_PROBE,
        imp_payload,
        blender_path=_env()["BLENDER_PATH"],
        quiet=True,
    )
    assert imp_result.get("errors") == [], imp_result
    imports = imp_result["data"]["imports"]
    assert len(imports) == 1
    row = imports[0]
    assert row["import_failed"] is False
    objs = row["objects"]
    names = {o["name"] for o in objs}

    # Support-only object must not be in exported asset
    assert "SupportCube" not in names

    # Visual mesh from layer collection must be present with stamped extras and baked subsurf geometry
    vis = next((o for o in objs if o["name"] == "Vis_fac_a" or "Vis_fac_a" in o["name"]), None)
    assert vis is not None, f"expected Vis_fac_a in {names}"
    assert vis["type"] == "MESH"
    assert vis["vertices"] >= 32, "subsurf apply should yield many more than 8 cube verts"
    extras = vis.get("extras") or {}
    assert extras.get("godot_type") == "mesh"
    assert extras.get("render_layers") == 1
