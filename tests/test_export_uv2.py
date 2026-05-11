"""End-to-end tests for `gleb export --bake-uv2` and the Godot import sidecar."""

from __future__ import annotations

import configparser
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

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


def _gleb_create(blend: Path, asset: str = "fac_a") -> None:
    p = _gleb(["create", str(blend), "--asset", asset, "--quiet"])
    assert p.returncode == 0, p.stdout + p.stderr


def _gleb_setup(blend: Path, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "blend_path": str(blend.resolve()),
        "assets": ["fac_a"],
        "visual_object_prefix": "Vis",
        "support_object_name": "SupportCube",
        "subsurf_levels": 2,
    }
    payload.update(extra)
    result, _ = run_blender_probe(blend, SETUP_PROBE, payload, blender_path=_env()["BLENDER_PATH"])
    assert result.get("errors") == [], result
    return result


def _gleb_export(blend: Path, output_dir: Path, *extra_args: str) -> dict[str, Any]:
    p = _gleb(
        [
            "export",
            str(blend),
            "--output-dir",
            str(output_dir),
            "--asset",
            "fac_a",
            "--quiet",
            *extra_args,
        ]
    )
    assert p.returncode == 0, p.stdout + p.stderr
    return json.loads(p.stdout)


def _import_glb(glb: Path) -> dict[str, Any]:
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
    return row


def _vis_object(row: dict[str, Any]) -> dict[str, Any]:
    objs = row["objects"]
    vis = next(
        (o for o in objs if o["type"] == "MESH" and "Vis_fac_a" in o["name"]),
        None,
    )
    assert vis is not None, f"no Vis_fac_a object in {[o['name'] for o in objs]}"
    return vis


pytestmark = [
    pytest.mark.skipif(not shutil.which("gleb"), reason="gleb CLI not on PATH"),
    pytest.mark.skipif(
        not Path(os.environ.get("BLENDER_PATH", "/usr/bin/blender")).is_file(),
        reason="Blender executable missing",
    ),
]


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------


def test_uv2_baked_into_glb(tmp_path: Path) -> None:
    blend = tmp_path / "rt.blend"
    out = tmp_path / "export"
    _gleb_create(blend)
    _gleb_setup(blend)

    er = _gleb_export(blend, out, "--bake-uv2", "--target-texel-density", "4")
    glb = out / "fac_a.glb"
    assert glb.is_file()

    entry = er["data"]["exports"][0]
    assert entry["status"] == "exported"
    assert entry["uv2_baked_meshes"] == 1
    assert entry["uv2_skipped_meshes"] == 0
    assert entry["lightmap_texel_size"] == pytest.approx(0.25)

    row = _import_glb(glb)
    vis = _vis_object(row)
    assert vis["uv_layers"] == 2
    assert vis["extras"]["godot_type"] == "mesh"
    assert vis["extras"]["lightmap_texel_size"] == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# 2. Array modifier baked before unwrap
# ---------------------------------------------------------------------------


def test_uv2_array_modifier_baked_before_unwrap(tmp_path: Path) -> None:
    """Verify modifier-bake-first: glTF must ship the Array-multiplied geometry,
    not the un-applied 8-vert source cube. Smart Project alone deduplicates
    identical Array copies, so the probe also runs a per-component grid pack
    after the unwrap to give each copy its own UV slot."""
    blend = tmp_path / "rt.blend"
    out = tmp_path / "export"
    _gleb_create(blend)
    _gleb_setup(blend, array_count=4, subsurf_levels=2)

    er = _gleb_export(blend, out, "--bake-uv2", "--target-texel-density", "4")
    glb = out / "fac_a.glb"
    row = _import_glb(glb)
    vis = _vis_object(row)
    assert vis["uv_layers"] == 2
    # If Array were NOT applied before glTF export (i.e., modifier-bake-first
    # ordering broken), glTF would ship the 8-vert source cube (export_apply
    # is forced False under --bake-uv2). subsurf-2 of one cube alone is ~98
    # verts; Array x4 of that is ~392 (more after glTF vertex splitting).
    assert vis["vertices"] >= 4 * 32, f"expected >= 128 verts, got {vis['vertices']}"

    entry = er["data"]["exports"][0]
    assert entry["uv2_baked_meshes"] == 1


# ---------------------------------------------------------------------------
# 3. Per-asset density override (collection custom property)
# ---------------------------------------------------------------------------


def test_uv2_per_asset_density_override(tmp_path: Path) -> None:
    blend = tmp_path / "rt.blend"
    out = tmp_path / "export"
    _gleb_create(blend)
    _gleb_setup(blend, asset_density_override=8.0)

    er = _gleb_export(blend, out, "--bake-uv2", "--target-texel-density", "4")
    entry = er["data"]["exports"][0]
    assert entry["lightmap_texel_size"] == pytest.approx(0.125), entry

    glb = out / "fac_a.glb"
    vis = _vis_object(_import_glb(glb))
    assert vis["extras"]["lightmap_texel_size"] == pytest.approx(0.125)


# ---------------------------------------------------------------------------
# 4. Collision meshes are not unwrapped
# ---------------------------------------------------------------------------


def test_uv2_skip_collision_meshes(tmp_path: Path) -> None:
    blend = tmp_path / "rt.blend"
    out = tmp_path / "export"
    _gleb_create(blend)
    _gleb_setup(blend, seed_collision=True)

    _gleb_export(blend, out, "--bake-uv2", "--target-texel-density", "4")
    glb = out / "fac_a.glb"
    row = _import_glb(glb)

    objs = row["objects"]
    vis = next(o for o in objs if "Vis_fac_a" in o["name"])
    col = next(o for o in objs if o["name"].startswith("Col_"))

    assert vis["uv_layers"] == 2
    assert vis["extras"].get("lightmap_texel_size") == pytest.approx(0.25)
    assert col["uv_layers"] <= 1
    assert col["extras"].get("godot_type") == "collision_trimesh"
    assert "lightmap_texel_size" not in col["extras"]


# ---------------------------------------------------------------------------
# 5. Pre-existing UV2 is honored, not overwritten
# ---------------------------------------------------------------------------


def test_uv2_honors_pre_existing_uv2(tmp_path: Path) -> None:
    blend = tmp_path / "rt.blend"
    out = tmp_path / "export"
    _gleb_create(blend)
    _gleb_setup(blend, pre_existing_uv2=True)

    er = _gleb_export(blend, out, "--bake-uv2", "--target-texel-density", "4")
    entry = er["data"]["exports"][0]
    assert entry["uv2_baked_meshes"] == 0
    assert entry["uv2_skipped_meshes"] == 1
    warns = " | ".join(er.get("warnings", []))
    assert "skipped UV2 unwrap" in warns or "already has" in warns

    vis = _vis_object(_import_glb(out / "fac_a.glb"))
    # glTF discards UV layer names (becomes TEXCOORD_0/1 -> "UVMap"/"UVMap.001"
    # on import). The skipped-count + warning above is the real proof we did
    # not re-unwrap; here we just confirm we did not add a third layer.
    assert vis["uv_layers"] == 2


# ---------------------------------------------------------------------------
# 6. Default-off is back-compat
# ---------------------------------------------------------------------------


def test_uv2_default_off_unchanged(tmp_path: Path) -> None:
    blend = tmp_path / "rt.blend"
    out = tmp_path / "export"
    _gleb_create(blend)
    _gleb_setup(blend)

    er = _gleb_export(blend, out)
    entry = er["data"]["exports"][0]
    assert entry["uv2_baked_meshes"] == 0
    assert entry["uv2_skipped_meshes"] == 0
    assert entry["lightmap_texel_size"] is None

    vis = _vis_object(_import_glb(out / "fac_a.glb"))
    assert vis["uv_layers"] == 1
    assert "lightmap_texel_size" not in vis["extras"]


# ---------------------------------------------------------------------------
# 7. UV0 stays as TEXCOORD_0 after bake
# ---------------------------------------------------------------------------


def test_uv2_uv0_remains_render_active(tmp_path: Path) -> None:
    """The setup probe stamps every UV0 loop with a sentinel value (0.42, 0.17)
    BEFORE export. After --bake-uv2 + glTF round-trip, the sentinel must still
    sit at slot 0 (TEXCOORD_0). If our code ever swapped active_render to UV2,
    the lightmap-packed coords would land in slot 0 and the sentinel would be
    gone — albedo / metallic / normal sampling in Godot would then read the
    lightmap UVs by accident."""
    blend = tmp_path / "rt.blend"
    out = tmp_path / "export"
    _gleb_create(blend)
    _gleb_setup(blend, custom_uv0_name="UVMap_Albedo")

    _gleb_export(blend, out, "--bake-uv2", "--target-texel-density", "4")
    vis = _vis_object(_import_glb(out / "fac_a.glb"))
    assert vis["uv_layers"] == 2
    sample = vis["uv0_sample"]
    assert sample is not None
    assert sample[0] == pytest.approx(0.42, abs=1e-3), sample
    assert sample[1] == pytest.approx(0.17, abs=1e-3), sample


# ---------------------------------------------------------------------------
# 8. Source .blend byte-identical after bake-export (swap/restore invariant)
# ---------------------------------------------------------------------------


def test_uv2_source_blend_byte_identical(tmp_path: Path) -> None:
    blend = tmp_path / "rt.blend"
    out = tmp_path / "export"
    _gleb_create(blend)
    _gleb_setup(blend, array_count=3)

    pre_hash = hashlib.sha256(blend.read_bytes()).hexdigest()
    _gleb_export(blend, out, "--bake-uv2", "--target-texel-density", "4")
    post_hash = hashlib.sha256(blend.read_bytes()).hexdigest()
    assert pre_hash == post_hash, "source .blend must not be modified by bake-export"


# ---------------------------------------------------------------------------
# 9. Sidecar is written when --write-import-sidecar is passed
# ---------------------------------------------------------------------------


def test_sidecar_written_when_flag_set(tmp_path: Path) -> None:
    blend = tmp_path / "rt.blend"
    out = tmp_path / "export"
    _gleb_create(blend)
    _gleb_setup(blend)

    er = _gleb_export(
        blend,
        out,
        "--bake-uv2",
        "--target-texel-density",
        "4",
        "--write-import-sidecar",
    )
    glb = out / "fac_a.glb"
    sidecar = out / "fac_a.glb.import"
    assert sidecar.is_file(), f"missing sidecar {sidecar}"

    cfg = configparser.ConfigParser()
    cfg.read(sidecar)
    assert cfg.get("remap", "importer").strip('"') == "scene"
    assert cfg.getint("params", "meshes/light_baking") == 2
    assert cfg.getfloat("params", "meshes/lightmap_texel_size") == pytest.approx(0.25)

    entry = er["data"]["exports"][0]
    assert entry["sidecar_path"] == str(sidecar)


# ---------------------------------------------------------------------------
# 10. Existing sidecar must NOT be overwritten
# ---------------------------------------------------------------------------


def test_sidecar_not_overwritten_if_present(tmp_path: Path) -> None:
    blend = tmp_path / "rt.blend"
    out = tmp_path / "export"
    out.mkdir(parents=True)
    sidecar = out / "fac_a.glb.import"
    marker = "# user-tweaked-marker-do-not-clobber\n"
    sidecar.write_text(marker, encoding="utf-8")

    _gleb_create(blend)
    _gleb_setup(blend)
    er = _gleb_export(
        blend,
        out,
        "--bake-uv2",
        "--target-texel-density",
        "4",
        "--write-import-sidecar",
    )

    assert sidecar.read_text(encoding="utf-8") == marker
    warns = " | ".join(er.get("warnings", []))
    assert "preserved" in warns and "fac_a.glb.import" in warns
    entry = er["data"]["exports"][0]
    assert entry["sidecar_path"] is None


# ---------------------------------------------------------------------------
# 11. No sidecar when --write-import-sidecar is omitted
# ---------------------------------------------------------------------------


def test_no_sidecar_without_flag(tmp_path: Path) -> None:
    blend = tmp_path / "rt.blend"
    out = tmp_path / "export"
    _gleb_create(blend)
    _gleb_setup(blend)

    _gleb_export(blend, out, "--bake-uv2", "--target-texel-density", "4")
    sidecar = out / "fac_a.glb.import"
    assert not sidecar.exists()


# ---------------------------------------------------------------------------
# 12. Excluded LayerCollection still bakes UV2 + restores
# ---------------------------------------------------------------------------


def test_uv2_excluded_layer_collection_still_baked(tmp_path: Path) -> None:
    blend = tmp_path / "rt.blend"
    out = tmp_path / "export"
    _gleb_create(blend)
    _gleb_setup(blend, exclude_asset_layer=True)

    pre_hash = hashlib.sha256(blend.read_bytes()).hexdigest()
    er = _gleb_export(blend, out, "--bake-uv2", "--target-texel-density", "4")
    post_hash = hashlib.sha256(blend.read_bytes()).hexdigest()
    assert pre_hash == post_hash, "source .blend must remain byte-identical"

    entry = er["data"]["exports"][0]
    assert entry["status"] == "exported"
    assert entry["uv2_baked_meshes"] == 1

    vis = _vis_object(_import_glb(out / "fac_a.glb"))
    assert vis["uv_layers"] == 2
