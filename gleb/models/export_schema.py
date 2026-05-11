"""Schemas for `gleb export` output."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ExportStatus = Literal["exported", "failed", "skipped"]


class AssetExport(BaseModel):
    asset: str
    path: str
    status: ExportStatus
    uv2_baked_meshes: int = 0
    uv2_skipped_meshes: int = 0
    lightmap_texel_size: float | None = None
    sidecar_path: str | None = None


class ExportMeta(BaseModel):
    file: str
    output_dir: str
    blender_version: str
    command: str = "export"


class ExportSummary(BaseModel):
    assets_exported: int = 0
    assets_skipped: int = 0
    assets_failed: int = 0


class ExportData(BaseModel):
    output_dir: str = ""
    exports: list[AssetExport] = Field(default_factory=list)


class ExportResult(BaseModel):
    meta: ExportMeta
    summary: ExportSummary = Field(default_factory=ExportSummary)
    data: ExportData = Field(default_factory=ExportData)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
