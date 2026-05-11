"""Schemas for `gleb compare` output."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from gleb.models.explore_schema import ExploreQuery, Scope


class CompareMeta(BaseModel):
    left_file: str
    right_file: str
    left_blender_version: str
    right_blender_version: str
    scope: Scope
    query: ExploreQuery = Field(default_factory=ExploreQuery)
    identical: bool


class CompareSummaryStats(BaseModel):
    """Roll-up statistics for the diff tree."""

    changed_paths: int = 0
    paths: list[str] = Field(default_factory=list)


class CompareChanges(BaseModel):
    """Nested diff for explore `summary` and `data` sections."""

    summary: dict[str, Any] | None = None
    explore_data: dict[str, Any] | None = None


class CompareDataPayload(BaseModel):
    changes: CompareChanges = Field(default_factory=CompareChanges)


class CompareResult(BaseModel):
    meta: CompareMeta
    summary: CompareSummaryStats = Field(default_factory=CompareSummaryStats)
    data: CompareDataPayload = Field(default_factory=CompareDataPayload)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
