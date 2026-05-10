"""Move root-level JPG/PNG into orig/ and emit half, quarter, eighth mip folders."""

from __future__ import annotations

import os
import shutil

from PIL import Image, UnidentifiedImageError

from gleb.texture_pipeline.log import TextureLog

DOWNSCALE_SUBDIRS = ("orig", "half", "quarter", "eighth")


def downscale_textures(directory: str, log: TextureLog | None = None) -> int:
    """
    Process root-level .jpg/.png: move to orig/, write half/quarter/eighth.
    Returns count of images processed.
    """
    orig_dir = os.path.join(directory, "orig")
    half_dir = os.path.join(directory, "half")
    quarter_dir = os.path.join(directory, "quarter")
    eighth_dir = os.path.join(directory, "eighth")

    os.makedirs(orig_dir, exist_ok=True)
    os.makedirs(half_dir, exist_ok=True)
    os.makedirs(quarter_dir, exist_ok=True)
    os.makedirs(eighth_dir, exist_ok=True)

    count = 0
    for file in os.listdir(directory):
        filepath = os.path.join(directory, file)

        if not (file.lower().endswith(".jpg") or file.lower().endswith(".png")):
            continue

        try:
            img = Image.open(filepath)
            count += 1

            orig_path = os.path.join(orig_dir, file)
            shutil.move(filepath, orig_path)

            half_size = (img.width // 2, img.height // 2)
            half_img = img.resize(half_size, Image.Resampling.LANCZOS)
            half_img.save(os.path.join(half_dir, file))

            quarter_size = (img.width // 4, img.height // 4)
            quarter_img = img.resize(quarter_size, Image.Resampling.LANCZOS)
            quarter_img.save(os.path.join(quarter_dir, file))

            eighth_size = (img.width // 8, img.height // 8)
            eighth_img = img.resize(eighth_size, Image.Resampling.LANCZOS)
            eighth_img.save(os.path.join(eighth_dir, file))

            if log:
                log.info(f"{file} -> orig, half, quarter, eighth")

        except (OSError, UnidentifiedImageError):
            if log:
                log.warn(f"skip: {file} (not a valid image)")

    if count == 0 and log:
        log.info("no images in directory")
    return count


def ensure_eighth_from_orig(directory: str, log: TextureLog | None = None) -> bool:
    """
    When directory has orig, half, quarter but no eighth: create eighth from orig.
    Returns True if eighth was created.
    """
    orig_dir = os.path.join(directory, "orig")
    eighth_dir = os.path.join(directory, "eighth")
    if not os.path.isdir(orig_dir) or os.path.isdir(eighth_dir):
        return False
    os.makedirs(eighth_dir, exist_ok=True)
    count = 0
    for file in os.listdir(orig_dir):
        filepath = os.path.join(orig_dir, file)
        if not (file.lower().endswith(".jpg") or file.lower().endswith(".png")):
            continue
        try:
            img = Image.open(filepath)
            eighth_size = (max(1, img.width // 8), max(1, img.height // 8))
            eighth_img = img.resize(eighth_size, Image.Resampling.LANCZOS)
            eighth_img.save(os.path.join(eighth_dir, file))
            count += 1
            if log:
                log.info(f"{file} -> eighth (from orig)")
        except (OSError, UnidentifiedImageError):
            if log:
                log.warn(f"skip: {file} (not a valid image)")
    return count > 0
