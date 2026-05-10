"""Host-side Godot texture pipeline (ORM, decals, downscale, import stubs)."""

from gleb.texture_pipeline.create_orm import (
    FILL_NO_AO,
    FILL_NO_METALNESS,
    FILL_NO_ROUGHNESS,
    create_orm_for_directory,
    create_orm_from_paths,
)
from gleb.texture_pipeline.log import TextureLog
from gleb.texture_pipeline.process import SetProcessRecord, process_path_structured

__all__ = [
    "FILL_NO_AO",
    "FILL_NO_METALNESS",
    "FILL_NO_ROUGHNESS",
    "TextureLog",
    "SetProcessRecord",
    "create_orm_for_directory",
    "create_orm_from_paths",
    "process_path_structured",
]
