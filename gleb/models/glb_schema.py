"""Schemas for `gleb glb` (inspect) and the .glb-mode of `gleb compare`."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Per-glb inspect result
# ---------------------------------------------------------------------------


class GlbMaterial(BaseModel):
    name: str
    use_nodes: bool = True
    blend_method: str | None = None
    use_backface_culling: bool = False
    diffuse_color: list[float] = Field(default_factory=list)
    metallic: float = 0.0
    roughness: float = 0.5
    principled_present: bool = False
    base_color_default: list[float] | None = None
    base_color_linked_from: str | None = None
    alpha_default: float | None = None
    alpha_linked_from: str | None = None


class GlbMaterialSlot(BaseModel):
    link: str = "DATA"
    material: GlbMaterial | None = None


class GlbObject(BaseModel):
    name: str
    type: str
    parent: str | None = None
    vertices: int = 0
    polygons: int = 0
    extras: dict[str, Any] = Field(default_factory=dict)
    uv_layers: int = 0
    uv_layer_names: list[str] = Field(default_factory=list)
    uv2_island_overlaps: bool = False
    uv0_sample: list[float] | None = None
    material_slots: list[GlbMaterialSlot] = Field(default_factory=list)
    polys_per_slot: dict[str, int] = Field(default_factory=dict)


class GlbInspect(BaseModel):
    path: str
    import_failed: bool = False
    objects: list[GlbObject] = Field(default_factory=list)


class GlbInspectMeta(BaseModel):
    blender_version: str = ""
    command: str = "glb"


class GlbInspectSummary(BaseModel):
    files_inspected: int = 0
    files_failed: int = 0
    objects_total: int = 0


class GlbInspectData(BaseModel):
    inspects: list[GlbInspect] = Field(default_factory=list)


class GlbInspectResult(BaseModel):
    meta: GlbInspectMeta = Field(default_factory=GlbInspectMeta)
    summary: GlbInspectSummary = Field(default_factory=GlbInspectSummary)
    data: GlbInspectData = Field(default_factory=GlbInspectData)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Diff between two glbs (or between paired files in two directories)
# ---------------------------------------------------------------------------


class GlbObjectDiff(BaseModel):
    name: str
    fields_changed: list[str] = Field(default_factory=list)
    left: dict[str, Any] = Field(default_factory=dict)
    right: dict[str, Any] = Field(default_factory=dict)


class GlbPairDiff(BaseModel):
    name: str
    left_path: str
    right_path: str
    identical: bool = True
    object_count_left: int = 0
    object_count_right: int = 0
    objects_only_in_left: list[str] = Field(default_factory=list)
    objects_only_in_right: list[str] = Field(default_factory=list)
    object_diffs: list[GlbObjectDiff] = Field(default_factory=list)


class GlbCompareMeta(BaseModel):
    left: str
    right: str
    blender_version: str = ""
    command: str = "compare-glb"
    identical: bool = False


class GlbCompareSummary(BaseModel):
    pairs: int = 0
    pairs_identical: int = 0
    pairs_changed: int = 0
    pairs_only_in_left: list[str] = Field(default_factory=list)
    pairs_only_in_right: list[str] = Field(default_factory=list)


class GlbCompareData(BaseModel):
    pairs: list[GlbPairDiff] = Field(default_factory=list)


class GlbCompareResult(BaseModel):
    meta: GlbCompareMeta
    summary: GlbCompareSummary = Field(default_factory=GlbCompareSummary)
    data: GlbCompareData = Field(default_factory=GlbCompareData)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
