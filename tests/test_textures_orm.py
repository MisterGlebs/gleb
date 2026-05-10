"""Tests for manual ORM packing."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

pytest.importorskip("numpy")


def test_create_orm_from_paths_explicit(tmp_path: Path) -> None:
    from gleb.texture_pipeline.create_orm import create_orm_from_paths

    ao = tmp_path / "ao.png"
    rough = tmp_path / "r.png"
    meta = tmp_path / "m.png"
    Image.new("L", (64, 64), 255).save(ao)
    Image.new("L", (64, 64), 128).save(rough)
    Image.new("L", (64, 64), 0).save(meta)
    out = tmp_path / "orm.png"

    path, w, h = create_orm_from_paths(
        output_path=out,
        ao_path=str(ao),
        roughness_path=str(rough),
        metallic_path=str(meta),
    )
    assert path == str(out.resolve())
    assert w == 64 and h == 64
    assert out.is_file()


def test_run_textures_orm_utils(tmp_path: Path) -> None:
    from gleb.commands.textures_utils import run_textures_orm

    ao = tmp_path / "a.png"
    Image.new("L", (48, 48), 100).save(ao)
    out = tmp_path / "packed.png"

    result = run_textures_orm(output=out, ao=ao, roughness=None, metallic=None)
    assert result.summary.width == 48
    assert result.summary.height == 48
    assert Path(result.data.output_path).is_file()
