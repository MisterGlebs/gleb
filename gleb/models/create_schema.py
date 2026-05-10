"""Schemas for `gleb create` output."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreateMeta(BaseModel):
    output: str
    blender_version: str
    command: str = "create"


class CreateSummary(BaseModel):
    collections_created: int = 0
    assets_created: int = 0


class CreateData(BaseModel):
    assets: list[str] = Field(default_factory=list)
    collections: list[str] = Field(default_factory=list)
    output_path: str = ""


class CreateResult(BaseModel):
    meta: CreateMeta
    summary: CreateSummary = Field(default_factory=CreateSummary)
    data: CreateData = Field(default_factory=CreateData)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
