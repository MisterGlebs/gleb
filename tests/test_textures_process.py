"""Tests for gleb.texture_pipeline batch processing."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

pytest.importorskip("numpy")


def _write_fab_set(directory: Path) -> None:
    for suffix, val in [("_ao", 200), ("_roughness", 128), ("_metalness", 10)]:
        img = Image.new("L", (32, 32), val)
        img.save(directory / f"mat{suffix}.png")


def test_process_single_fab_texture_set(tmp_path: Path) -> None:
    from gleb.texture_pipeline.process import process_path_structured

    _write_fab_set(tmp_path)
    records, log = process_path_structured(str(tmp_path))

    assert len(records) == 1
    assert records[0].outcome.startswith("texture (FAB)")
    # Downscale moves root PNGs into orig/, including the packed ORM.
    assert (tmp_path / "orig" / "mat_ORM.png").is_file()
    assert (tmp_path / "orig").is_dir()
    assert (tmp_path / "half").is_dir()
    assert not log.warnings or isinstance(log.warnings, list)


def test_process_unknown_set_skipped(tmp_path: Path) -> None:
    from gleb.texture_pipeline.process import process_path_structured

    (tmp_path / "random.png").write_bytes(b"not an image")
    records, _ = process_path_structured(str(tmp_path))
    assert len(records) == 1
    assert "skip" in records[0].outcome.lower()


def test_process_path_not_dir_raises(tmp_path: Path) -> None:
    from gleb.texture_pipeline.process import process_path_structured

    with pytest.raises(FileNotFoundError):
        process_path_structured(str(tmp_path / "nope"))
