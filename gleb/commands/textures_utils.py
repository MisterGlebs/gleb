"""Orchestration for `gleb textures` commands."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from gleb.models.textures_schema import (
    SetOutcomeRow,
    TexturesOrmData,
    TexturesOrmMeta,
    TexturesOrmResult,
    TexturesOrmSummary,
    TexturesProcessData,
    TexturesProcessMeta,
    TexturesProcessResult,
    TexturesProcessSummary,
)


def run_textures_process(
    path: Path,
    *,
    progress: Callable[[str], None] | None = None,
) -> TexturesProcessResult:
    """Run batch texture processing; raises FileNotFoundError if path is invalid."""
    from gleb.texture_pipeline.process import process_path_structured

    records, log = process_path_structured(str(path.resolve()), progress=progress)
    skipped = sum(1 for r in records if r.outcome.startswith("skip:"))
    sets_data = [SetOutcomeRow(name=r.set_name, outcome=r.outcome) for r in records]
    return TexturesProcessResult(
        meta=TexturesProcessMeta(path=str(path.resolve())),
        summary=TexturesProcessSummary(sets_total=len(records), sets_skipped=skipped),
        data=TexturesProcessData(
            sets=sets_data,
            messages=list(log.infos),
        ),
        warnings=list(log.warnings),
        errors=[],
    )


def run_textures_orm(
    *,
    output: Path,
    ao: Path | None,
    roughness: Path | None,
    metallic: Path | None,
) -> TexturesOrmResult:
    """Create a single ORM PNG from explicit inputs."""
    from gleb.texture_pipeline.create_orm import create_orm_from_paths
    from gleb.texture_pipeline.log import TextureLog

    log = TextureLog()
    out_abs, w, h = create_orm_from_paths(
        output_path=output,
        ao_path=str(ao.resolve()) if ao else None,
        roughness_path=str(roughness.resolve()) if roughness else None,
        metallic_path=str(metallic.resolve()) if metallic else None,
        log=log,
    )
    return TexturesOrmResult(
        meta=TexturesOrmMeta(
            output=str(output.resolve()),
            ao=str(ao.resolve()) if ao else None,
            roughness=str(roughness.resolve()) if roughness else None,
            metallic=str(metallic.resolve()) if metallic else None,
        ),
        summary=TexturesOrmSummary(width=w, height=h),
        data=TexturesOrmData(output_path=out_abs, messages=list(log.infos)),
        warnings=list(log.warnings),
        errors=[],
    )


def ensure_texture_dependencies() -> None:
    """Raise ImportError with a clear message if numpy/Pillow are missing."""
    try:
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "Texture commands require optional dependencies. "
            "Install with: pip install 'gleb[textures]'"
        ) from exc
