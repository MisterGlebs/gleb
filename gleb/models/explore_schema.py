"""Schemas for `gleb explore` output."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Scope = Literal[
    "all",
    "scene",
    "collections",
    "objects",
    "materials",
    "modifiers",
    "animations",
    "relations",
    "constraints",
    "geometry",
    "textures",
    "armatures",
    "libraries",
    "custom_properties",
]
MatchMode = Literal["exact", "contains", "regex"]


class ExploreQuery(BaseModel):
    object_names: list[str] = Field(default_factory=list)
    match: MatchMode = "exact"
    ignore_case: bool = False


class ExploreMeta(BaseModel):
    file: str
    blender_version: str
    scope: Scope
    query: ExploreQuery = Field(default_factory=ExploreQuery)


class ExploreSummary(BaseModel):
    collections: int = 0
    relations: int = 0
    objects: int = 0
    materials: int = 0
    animations: int = 0
    constraints: int = 0
    geometry: int = 0
    textures: int = 0
    armatures: int = 0
    libraries: int = 0
    custom_properties: int = 0
    diagnostics: int = 0


class ExploreStructure(BaseModel):
    collections: list[dict[str, Any]] = Field(default_factory=list)
    relations: list[dict[str, Any]] = Field(default_factory=list)


class ExploreData(BaseModel):
    structure: ExploreStructure = Field(default_factory=ExploreStructure)
    scene: dict[str, Any] = Field(default_factory=dict)
    objects: list[dict[str, Any]] = Field(default_factory=list)
    materials: list[dict[str, Any]] = Field(default_factory=list)
    modifiers: list[dict[str, Any]] = Field(default_factory=list)
    animations: list[dict[str, Any]] = Field(default_factory=list)
    constraints: list[dict[str, Any]] = Field(default_factory=list)
    geometry: list[dict[str, Any]] = Field(default_factory=list)
    textures: list[dict[str, Any]] = Field(default_factory=list)
    armatures: list[dict[str, Any]] = Field(default_factory=list)
    libraries: list[dict[str, Any]] = Field(default_factory=list)
    custom_properties: list[dict[str, Any]] = Field(default_factory=list)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)


class ExploreResult(BaseModel):
    meta: ExploreMeta
    summary: ExploreSummary = Field(default_factory=ExploreSummary)
    data: ExploreData = Field(default_factory=ExploreData)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
