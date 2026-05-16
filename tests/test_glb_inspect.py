"""Tests for `gleb glb show` and the .glb-mode of `gleb compare`.

Covers:
- Diff helpers in gleb.commands.glb_utils (no Blender required).
- run_glb_inspect end-to-end against a real exported .glb (Blender required).
- `gleb glb show` CLI: emits a valid envelope, includes material slots and
  polys-per-slot in the per-object payload.
- `gleb compare` CLI in .glb-pair mode: identical pair → exit 0, mismatched
  pair → exit 1 with structural diff fields populated.
- `gleb compare` CLI in .glb-dir-pair mode: pairs files by basename, reports
  pairs_only_in_left / pairs_only_in_right.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from gleb.commands.glb_utils import (
    diff_summary_lines,
    is_glb_compare_pair,
    run_glb_compare,
    run_glb_inspect,
    tracked_fields,
)
from gleb.models.glb_schema import (
    GlbCompareResult,
    GlbInspect,
    GlbInspectResult,
    GlbObject,
)

ROOT = Path(__file__).resolve().parents[1]


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


def _make_obj(name: str, **overrides: Any) -> GlbObject:
    base = {
        "name": name,
        "type": "MESH",
        "parent": None,
        "vertices": 8,
        "polygons": 6,
        "extras": {"godot_type": "mesh"},
        "uv_layers": 1,
        "uv_layer_names": ["UVMap"],
        "uv2_island_overlaps": False,
        "uv0_sample": [0.0, 0.0],
        "material_slots": [],
        "polys_per_slot": {"0": 6},
    }
    base.update(overrides)
    return GlbObject.model_validate(base)


# ---------------------------------------------------------------------------
# Pure-Python diff helpers (no Blender)
# ---------------------------------------------------------------------------


def test_tracked_fields_is_stable_documented_set() -> None:
    fields = tracked_fields()
    assert "extras" in fields
    assert "material_slots" in fields
    assert "polys_per_slot" in fields
    assert "uv_layers" in fields
    # Frozen membership; if you add a tracked field, update this set too.
    assert set(fields) == {
        "type",
        "parent",
        "vertices",
        "polygons",
        "uv_layers",
        "uv_layer_names",
        "uv2_island_overlaps",
        "uv0_sample",
        "extras",
        "material_slots",
        "polys_per_slot",
    }


def test_is_glb_compare_pair_routing(tmp_path: Path) -> None:
    a = tmp_path / "a.glb"
    b = tmp_path / "b.glb"
    a.write_bytes(b"")
    b.write_bytes(b"")
    assert is_glb_compare_pair(a, b) is True

    blend = tmp_path / "x.blend"
    blend.write_bytes(b"")
    assert is_glb_compare_pair(blend, b) is False
    assert is_glb_compare_pair(a, blend) is False

    da = tmp_path / "da"
    db = tmp_path / "db"
    da.mkdir()
    db.mkdir()
    # Empty dirs → not a glb compare pair
    assert is_glb_compare_pair(da, db) is False
    (da / "x.glb").write_bytes(b"")
    (db / "x.glb").write_bytes(b"")
    assert is_glb_compare_pair(da, db) is True


def test_diff_summary_lines_renders_structural_changes() -> None:
    left_ins = GlbInspect(
        path="/l/asset.glb",
        objects=[_make_obj("Vis"), _make_obj("Helper")],
    )
    right_ins = GlbInspect(
        path="/r/asset.glb",
        objects=[
            _make_obj("Vis", uv_layers=2, uv_layer_names=["UVMap", "UV2"]),
            _make_obj("Extra"),
        ],
    )
    from gleb.models.glb_schema import (
        GlbCompareData,
        GlbCompareMeta,
        GlbCompareSummary,
    )
    from gleb.commands.glb_utils import _diff_pair  # type: ignore[attr-defined]

    pair = _diff_pair("asset.glb", left_ins, right_ins)
    assert pair.identical is False
    assert pair.objects_only_in_left == ["Helper"]
    assert pair.objects_only_in_right == ["Extra"]
    assert len(pair.object_diffs) == 1
    diff = pair.object_diffs[0]
    assert diff.name == "Vis"
    assert "uv_layers" in diff.fields_changed
    assert "uv_layer_names" in diff.fields_changed

    result = GlbCompareResult(
        meta=GlbCompareMeta(left="/l", right="/r", identical=False),
        summary=GlbCompareSummary(pairs=1, pairs_identical=0, pairs_changed=1),
        data=GlbCompareData(pairs=[pair]),
    )
    lines = diff_summary_lines(result)
    blob = "\n".join(lines)
    assert "asset.glb" in blob
    assert "uv_layers" in blob
    assert "missing in right" in blob
    assert "extra in right" in blob


def test_diff_pair_reports_extras_change_only() -> None:
    from gleb.commands.glb_utils import _diff_pair  # type: ignore[attr-defined]

    left_ins = GlbInspect(path="l.glb", objects=[_make_obj("Vis")])
    right_ins = GlbInspect(
        path="r.glb",
        objects=[_make_obj("Vis", extras={"godot_type": "mesh", "lightmap_texel_size": 0.25})],
    )
    pair = _diff_pair("x.glb", left_ins, right_ins)
    assert pair.identical is False
    assert len(pair.object_diffs) == 1
    assert pair.object_diffs[0].fields_changed == ["extras"]


def test_diff_pair_identical_returns_empty_diff() -> None:
    from gleb.commands.glb_utils import _diff_pair  # type: ignore[attr-defined]

    left_ins = GlbInspect(path="l.glb", objects=[_make_obj("A"), _make_obj("B")])
    right_ins = GlbInspect(path="r.glb", objects=[_make_obj("A"), _make_obj("B")])
    pair = _diff_pair("x.glb", left_ins, right_ins)
    assert pair.identical is True
    assert pair.object_diffs == []
    assert pair.objects_only_in_left == []
    assert pair.objects_only_in_right == []


# ---------------------------------------------------------------------------
# Blender-required end-to-end tests
# ---------------------------------------------------------------------------


_blender_present = pytest.mark.skipif(
    not Path(os.environ.get("BLENDER_PATH", "/usr/bin/blender")).is_file(),
    reason="Blender executable missing",
)
_cli_present = pytest.mark.skipif(not shutil.which("gleb"), reason="gleb CLI not on PATH")


def _gleb_create(blend: Path, asset: str = "fac_a") -> None:
    p = _gleb(["create", str(blend), "--asset", asset, "--quiet"])
    assert p.returncode == 0, p.stdout + p.stderr


def _gleb_setup(blend: Path) -> None:
    """Seed a single visual cube via the existing roundtrip setup probe."""
    from gleb.core.blender_runner import run_blender_probe

    setup_probe = ROOT / "gleb" / "blender_scripts" / "roundtrip_setup_probe.py"
    payload = {
        "blend_path": str(blend.resolve()),
        "assets": ["fac_a"],
        "visual_object_prefix": "Vis",
        "support_object_name": "SupportCube",
        "subsurf_levels": 1,
    }
    result, _ = run_blender_probe(blend, setup_probe, payload, blender_path=_env()["BLENDER_PATH"])
    assert result.get("errors") == [], result


def _gleb_export(blend: Path, out_dir: Path, *extra: str) -> dict[str, Any]:
    p = _gleb(
        [
            "export",
            str(blend),
            "--output-dir",
            str(out_dir),
            "--asset",
            "fac_a",
            "--quiet",
            *extra,
        ]
    )
    assert p.returncode == 0, p.stdout + p.stderr
    return json.loads(p.stdout)


@_blender_present
@_cli_present
def test_run_glb_inspect_collects_material_slots_and_polys_per_slot(tmp_path: Path) -> None:
    blend = tmp_path / "rt.blend"
    out = tmp_path / "exp"
    _gleb_create(blend)
    _gleb_setup(blend)
    _gleb_export(blend, out)
    glb = out / "fac_a.glb"
    assert glb.is_file()

    result = run_glb_inspect([glb])
    assert isinstance(result, GlbInspectResult)
    assert result.summary.files_inspected == 1
    assert result.summary.files_failed == 0
    assert result.errors == []
    inspect = result.data.inspects[0]
    assert inspect.import_failed is False
    vis = next((o for o in inspect.objects if o.type == "MESH" and "Vis" in o.name), None)
    assert vis is not None, [o.name for o in inspect.objects]
    # Probe extension fields are present even with the default material setup.
    assert isinstance(vis.material_slots, list)
    assert isinstance(vis.polys_per_slot, dict)
    # If there is at least one slot referenced by polygons, the keys are slot indices.
    if vis.polygons > 0 and vis.polys_per_slot:
        assert all(isinstance(k, str) and k.isdigit() for k in vis.polys_per_slot.keys())
        assert sum(vis.polys_per_slot.values()) == vis.polygons


@_blender_present
@_cli_present
def test_glb_show_cli_emits_valid_envelope(tmp_path: Path) -> None:
    blend = tmp_path / "rt.blend"
    out = tmp_path / "exp"
    _gleb_create(blend)
    _gleb_setup(blend)
    _gleb_export(blend, out)
    glb = out / "fac_a.glb"

    p = _gleb(["glb", "show", str(glb)])
    assert p.returncode == 0, p.stdout + p.stderr
    payload = json.loads(p.stdout)
    assert payload["meta"]["command"] == "glb"
    assert payload["summary"]["files_inspected"] == 1
    assert payload["summary"]["files_failed"] == 0
    assert payload["data"]["inspects"][0]["import_failed"] is False
    objs = payload["data"]["inspects"][0]["objects"]
    assert any(o["type"] == "MESH" for o in objs)
    # Probe extension fields are surfaced through the CLI.
    sample = next(o for o in objs if o["type"] == "MESH")
    assert "material_slots" in sample
    assert "polys_per_slot" in sample
    assert "parent" in sample


@_blender_present
@_cli_present
def test_compare_glb_identical_pair_exits_zero(tmp_path: Path) -> None:
    """Comparing a .glb to itself must report identical and exit 0."""
    blend = tmp_path / "rt.blend"
    out = tmp_path / "exp"
    _gleb_create(blend)
    _gleb_setup(blend)
    _gleb_export(blend, out)
    glb = out / "fac_a.glb"

    p = _gleb(["compare", str(glb), str(glb)])
    assert p.returncode == 0, p.stdout + p.stderr
    payload = json.loads(p.stdout)
    assert payload["meta"]["identical"] is True
    assert payload["summary"]["pairs"] == 1
    assert payload["summary"]["pairs_changed"] == 0


@_blender_present
@_cli_present
def test_compare_glb_changed_pair_exits_one_with_field_diffs(tmp_path: Path) -> None:
    blend = tmp_path / "rt.blend"
    no_uv2 = tmp_path / "no_uv2"
    with_uv2 = tmp_path / "with_uv2"
    _gleb_create(blend)
    _gleb_setup(blend)
    _gleb_export(blend, no_uv2)
    _gleb_export(blend, with_uv2, "--bake-uv2", "--target-texel-density", "4")

    p = _gleb(["compare", str(no_uv2 / "fac_a.glb"), str(with_uv2 / "fac_a.glb")])
    assert p.returncode == 1, p.stdout + p.stderr
    payload = json.loads(p.stdout)
    assert payload["meta"]["identical"] is False
    assert payload["summary"]["pairs"] == 1
    pair = payload["data"]["pairs"][0]
    # Same object names on both sides — no orphan-drop, no rename leak.
    assert pair["objects_only_in_left"] == []
    assert pair["objects_only_in_right"] == []
    # Every Vis_fac_a object should report uv_layers + uv_layer_names + extras
    # as the changed fields between baseline and bake.
    assert pair["object_diffs"], pair
    sample = pair["object_diffs"][0]
    assert "uv_layers" in sample["fields_changed"]
    assert "extras" in sample["fields_changed"]


@_blender_present
@_cli_present
def test_compare_glb_directory_pair_pairs_by_basename(tmp_path: Path) -> None:
    """Two dirs of glbs: pair by basename, report pairs_only_in_* for unmatched."""
    blend_a = tmp_path / "a.blend"
    blend_b = tmp_path / "b.blend"
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    _gleb_create(blend_a, asset="fac_a")
    _gleb_create(blend_b, asset="fac_b")
    _gleb_setup(blend_a)
    # b.blend's roundtrip setup uses fac_a, but we want fac_b — overwrite via a fresh _gleb_setup style call:
    from gleb.core.blender_runner import run_blender_probe

    setup_probe = ROOT / "gleb" / "blender_scripts" / "roundtrip_setup_probe.py"
    run_blender_probe(
        blend_b,
        setup_probe,
        {
            "blend_path": str(blend_b.resolve()),
            "assets": ["fac_b"],
            "visual_object_prefix": "Vis",
            "support_object_name": "SupportCube",
            "subsurf_levels": 1,
        },
        blender_path=_env()["BLENDER_PATH"],
    )
    _gleb(["export", str(blend_a), "--output-dir", str(out_a), "--asset", "fac_a", "--quiet"])
    _gleb(["export", str(blend_b), "--output-dir", str(out_b), "--asset", "fac_b", "--quiet"])

    # out_a has fac_a.glb; out_b has fac_b.glb — no common basename.
    p = _gleb(["compare", str(out_a), str(out_b)])
    assert p.returncode == 1, p.stdout + p.stderr
    payload = json.loads(p.stdout)
    assert payload["summary"]["pairs"] == 0
    assert payload["summary"]["pairs_only_in_left"] == ["fac_a.glb"]
    assert payload["summary"]["pairs_only_in_right"] == ["fac_b.glb"]
    assert payload["meta"]["identical"] is False

    # Now copy fac_a.glb into both dirs to create a matched pair.
    shutil.copy(out_a / "fac_a.glb", out_b / "fac_a.glb")
    p = _gleb(["compare", str(out_a), str(out_b)])
    # fac_a.glb pair is identical, but fac_b.glb is still only-in-right → exit 1.
    assert p.returncode == 1, p.stdout + p.stderr
    payload = json.loads(p.stdout)
    assert payload["summary"]["pairs"] == 1
    assert payload["summary"]["pairs_identical"] == 1
    assert payload["summary"]["pairs_only_in_right"] == ["fac_b.glb"]


@_blender_present
@_cli_present
def test_compare_rejects_mixed_blend_glb(tmp_path: Path) -> None:
    blend = tmp_path / "rt.blend"
    out = tmp_path / "exp"
    _gleb_create(blend)
    _gleb_setup(blend)
    _gleb_export(blend, out)
    glb = out / "fac_a.glb"

    p = _gleb(["compare", str(blend), str(glb)])
    assert p.returncode == 1
    payload = json.loads(p.stdout)
    assert "cannot mix" in payload["errors"][0].lower()
