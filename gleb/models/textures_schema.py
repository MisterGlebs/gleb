"""Schemas for `gleb textures` host-side commands."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TexturesProcessMeta(BaseModel):
    runtime: Literal["host"] = "host"
    command: Literal["textures.process"] = "textures.process"
    path: str


class TexturesProcessSummary(BaseModel):
    sets_total: int = 0
    sets_skipped: int = 0


class SetOutcomeRow(BaseModel):
    name: str
    outcome: str


class TexturesProcessData(BaseModel):
    sets: list[SetOutcomeRow] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)


class TexturesProcessResult(BaseModel):
    meta: TexturesProcessMeta
    summary: TexturesProcessSummary = Field(default_factory=TexturesProcessSummary)
    data: TexturesProcessData = Field(default_factory=TexturesProcessData)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class TexturesOrmMeta(BaseModel):
    runtime: Literal["host"] = "host"
    command: Literal["textures.orm"] = "textures.orm"
    output: str
    ao: str | None = None
    roughness: str | None = None
    metallic: str | None = None


class TexturesOrmSummary(BaseModel):
    width: int = 0
    height: int = 0


class TexturesOrmData(BaseModel):
    output_path: str
    messages: list[str] = Field(default_factory=list)


class TexturesOrmResult(BaseModel):
    meta: TexturesOrmMeta
    summary: TexturesOrmSummary = Field(default_factory=TexturesOrmSummary)
    data: TexturesOrmData = Field(default_factory=TexturesOrmData)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
