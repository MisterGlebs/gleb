"""Schemas for `gleb edit` output."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

OperationStatus = Literal["applied", "skipped", "failed", "would_apply", "would_skip"]


class OperationResult(BaseModel):
    index: int
    type: str
    status: OperationStatus
    detail: str = ""


class EditMeta(BaseModel):
    file: str
    blender_version: str
    command: str = "edit"
    dry_run: bool = False
    operations_count: int = 0


class EditSummary(BaseModel):
    operations_total: int = 0
    operations_applied: int = 0
    operations_skipped: int = 0
    operations_failed: int = 0


class EditData(BaseModel):
    operation_results: list[OperationResult] = Field(default_factory=list)


class EditResult(BaseModel):
    meta: EditMeta
    summary: EditSummary = Field(default_factory=EditSummary)
    data: EditData = Field(default_factory=EditData)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
