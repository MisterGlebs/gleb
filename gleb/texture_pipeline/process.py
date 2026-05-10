"""Orchestrate texture set processing: ORM, decals, downscale, Godot import stubs."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass

from gleb.texture_pipeline.create_orm import create_orm_for_directory
from gleb.texture_pipeline.decal import process_decals
from gleb.texture_pipeline.downscale import downscale_textures, ensure_eighth_from_orig
from gleb.texture_pipeline.import_stub import write_orm_import_stubs_for_downscale
from gleb.texture_pipeline.log import TextureLog


def _list_images(directory: str) -> list[str]:
    return [
        f
        for f in os.listdir(directory)
        if os.path.isfile(os.path.join(directory, f))
        and f.lower().endswith((".jpg", ".jpeg", ".png", ".exr"))
    ]


def _is_decal_set(directory: str) -> bool:
    files = _list_images(directory)
    lower = [f.lower() for f in files]
    has_base = any("basecolor" in f for f in lower)
    has_opacity = any("opacity" in f for f in lower)
    return bool(has_base and has_opacity)


def _is_texture_set(directory: str) -> bool:
    files = _list_images(directory)
    bases = [os.path.splitext(f)[0].lower() for f in files]
    if any(b.endswith("_ao") or b.endswith("_roughness") or b.endswith("_metalness") for b in bases):
        return True
    lower = [f.lower() for f in files]
    if any("_arm_" in f for f in lower):
        return True
    if any("_ao_" in f or "_rough_" in f or "_metal_" in f for f in lower):
        return True
    return False


def _has_downscale_dirs(directory: str) -> bool:
    subdirs = {d for d in os.listdir(directory) if os.path.isdir(os.path.join(directory, d))}
    return subdirs >= {"orig", "half", "quarter"}


def _flatten_textures_subdir(directory: str, set_name: str, log: TextureLog) -> bool:
    textures_dir = os.path.join(directory, "textures")
    if not os.path.isdir(textures_dir):
        return False
    moved = 0
    for f in os.listdir(textures_dir):
        src = os.path.join(textures_dir, f)
        if os.path.isfile(src):
            dst = os.path.join(directory, f)
            if os.path.exists(dst):
                continue
            shutil.move(src, dst)
            moved += 1
    if moved:
        log.info(f"Move images from textures/ up: {set_name} ({moved} files)")
    return moved > 0


def _texture_convention(directory: str) -> str:
    files = _list_images(directory)
    bases = [os.path.splitext(f)[0].lower() for f in files]
    if any(b.endswith("_ao") or b.endswith("_roughness") or b.endswith("_metalness") for b in bases):
        return "FAB"
    return "Polyhaven"


@dataclass
class SetProcessRecord:
    set_name: str
    outcome: str


def _notify_progress(
    progress: Callable[[str], None] | None,
    message: str,
) -> None:
    if progress:
        progress(message)


def _process_set_dir(
    directory: str,
    *,
    root_path: str,
    log: TextureLog,
    progress: Callable[[str], None] | None = None,
) -> SetProcessRecord | None:
    directory = os.path.normpath(os.path.abspath(directory))
    if not os.path.isdir(directory):
        return None

    images = _list_images(directory)

    rel = os.path.relpath(directory, root_path).replace("\\", "/")
    if rel == ".":
        rel = os.path.basename(directory)
    set_name = rel

    if _has_downscale_dirs(directory):
        log.info(f"--- {set_name} ---")
        _notify_progress(progress, f"Set «{set_name}» (pre-tiered orig/half/quarter)")
        eighth_created = False
        if not os.path.isdir(os.path.join(directory, "eighth")):
            _notify_progress(progress, "  Adding eighth mip from orig…")
            log.info(f"Create eighth from orig (only 3 levels existed): {set_name}")
            eighth_created = ensure_eighth_from_orig(directory, log)
        _notify_progress(progress, "  Packing ORM in each mip folder…")
        log.info(f"Create ORM in orig, half, quarter, eighth: {set_name}")
        for sub in ("orig", "half", "quarter", "eighth"):
            subpath = os.path.join(directory, sub)
            if os.path.isdir(subpath):
                sub_log = TextureLog()
                create_orm_for_directory(subpath, sub_log)
                log.infos.extend(sub_log.infos)
                log.warnings.extend(sub_log.warnings)
        res_prefix = "res://" + set_name
        _notify_progress(progress, "  Writing Godot .import stubs…")
        log.info(f"Write .import stubs for ORM: {set_name}")
        write_orm_import_stubs_for_downscale(directory, res_prefix, log)
        if eighth_created:
            return SetProcessRecord(set_name, "already had orig/half/quarter (eighth added)")
        if os.path.isdir(os.path.join(directory, "eighth")):
            return SetProcessRecord(set_name, "already had orig/half/quarter/eighth")
        return SetProcessRecord(set_name, "already had orig/half/quarter")

    _flatten_textures_subdir(directory, set_name, log)
    images = _list_images(directory)

    if not images:
        log.info(f"--- {set_name} ---")
        log.info(f"Skip (no images): {set_name}")
        _notify_progress(progress, f"Set «{set_name}» — skipped (no images)")
        return SetProcessRecord(set_name, "skip: no images")

    log.info(f"--- {set_name} ---")
    _notify_progress(progress, f"Set «{set_name}»")

    if _is_decal_set(directory):
        _notify_progress(progress, "  Megascans decal: Albedo + ORM…")
        log.info(f"Create Albedo + ORM (decal/Megascans): {set_name}")
        process_decals(directory, log)
        _notify_progress(progress, "  Downscaling to orig / half / quarter / eighth…")
        log.info(f"Downscale -> orig, half, quarter, eighth: {set_name}")
        downscale_textures(directory, log)
        res_prefix = "res://" + set_name
        _notify_progress(progress, "  Writing Godot .import stubs…")
        log.info(f"Write .import stubs for ORM: {set_name}")
        write_orm_import_stubs_for_downscale(directory, res_prefix, log)
        return SetProcessRecord(set_name, "decal (Megascans)")
    if _is_texture_set(directory):
        conv = _texture_convention(directory)
        _notify_progress(progress, f"  Packing ORM ({conv})…")
        log.info(f"Create ORM (texture {conv}): {set_name}")
        create_orm_for_directory(directory, log)
        _notify_progress(progress, "  Downscaling to orig / half / quarter / eighth…")
        log.info(f"Downscale -> orig, half, quarter, eighth: {set_name}")
        downscale_textures(directory, log)
        res_prefix = "res://" + set_name
        _notify_progress(progress, "  Writing Godot .import stubs…")
        log.info(f"Write .import stubs for ORM: {set_name}")
        write_orm_import_stubs_for_downscale(directory, res_prefix, log)
        return SetProcessRecord(set_name, f"texture ({conv})")

    _notify_progress(progress, "  Skipped — not decal / FAB / Polyhaven")
    log.info(f"Skip (unknown set, not decal or FAB/Polyhaven): {set_name}")
    return SetProcessRecord(set_name, "skip: unknown set")


def process_path_structured(
    path: str,
    *,
    progress: Callable[[str], None] | None = None,
) -> tuple[list[SetProcessRecord], TextureLog]:
    """
    Process a directory (single set) or a parent of multiple set directories.
    Returns per-set records and a TextureLog with all infos and warnings.

    ``progress`` is called with short human-readable phase lines (for stderr UI).
    """
    log = TextureLog()
    path = os.path.normpath(os.path.abspath(path))
    if not os.path.isdir(path):
        raise FileNotFoundError(f"Not a directory: {path}")

    subdirs = [
        os.path.join(path, d) for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))
    ]

    results: list[SetProcessRecord] = []

    if subdirs and not _has_downscale_dirs(path):
        log.info(f"--- {path} ---")
        log.info(f"Processing {len(subdirs)} sets")
        _notify_progress(progress, f"Processing {len(subdirs)} texture sets under {path}")
        for sub in subdirs:
            r = _process_set_dir(sub, root_path=path, log=log, progress=progress)
            if r:
                results.append(r)
        log.info("Summary")
        for rec in results:
            log.info(f"  {rec.set_name}  ->  {rec.outcome}")
        _notify_progress(progress, "Done.")
        return results, log

    _notify_progress(progress, f"Processing {path}")
    r = _process_set_dir(path, root_path=path, log=log, progress=progress)
    if r:
        results.append(r)
    log.info("Summary")
    for rec in results:
        log.info(f"  {rec.set_name}  ->  {rec.outcome}")
    _notify_progress(progress, "Done.")
    return results, log
