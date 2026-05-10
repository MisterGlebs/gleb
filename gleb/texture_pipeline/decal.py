"""Megascans-style decal folder: BaseColor + Opacity -> Albedo + ORM."""

from __future__ import annotations

import os

from PIL import Image

from gleb.texture_pipeline.log import TextureLog


def process_decals(directory: str, log: TextureLog | None = None) -> tuple[str | None, str | None]:
    """
    Build Albedo (RGBA) and ORM from Megascans-style filenames in ``directory``.
    Returns (albedo_path or None, orm_path or None).
    """
    basecolor = None
    opacity = None
    ao = None
    roughness = None
    metallic = None

    for file in os.listdir(directory):
        filepath = os.path.join(directory, file)
        if "BaseColor" in file and file.endswith(".jpg"):
            basecolor = filepath
        elif "Opacity" in file and file.endswith(".jpg"):
            opacity = filepath
        elif "AO" in file and file.endswith(".jpg"):
            ao = filepath
        elif "Roughness" in file and file.endswith(".jpg"):
            roughness = filepath
        elif "Metallic" in file and file.endswith(".jpg"):
            metallic = filepath

    albedo_path = None
    if basecolor and opacity:
        base_img = Image.open(basecolor).convert("RGBA")
        opacity_img = Image.open(opacity).convert("L")
        base_img.putalpha(opacity_img)
        name = os.path.splitext(os.path.basename(basecolor))[0].split("_BaseColor")[0]
        albedo_path = os.path.join(directory, f"{name}_Albedo.png")
        base_img.save(albedo_path)
        if log:
            log.info(f"albedo: {os.path.basename(albedo_path)}")

    width, height = (None, None)
    if ao:
        ao_img = Image.open(ao).convert("L")
        width, height = ao_img.size
    else:
        width = width or 1024
        height = height or 1024
        ao_img = Image.new("L", (width, height), 255)

    if roughness:
        roughness_img = Image.open(roughness).convert("L")
    else:
        roughness_img = Image.new("L", (width, height), 255)

    if metallic:
        metallic_img = Image.open(metallic).convert("L")
    else:
        metallic_img = Image.new("L", (width, height), 0)

    orm_img = Image.merge("RGB", (ao_img, roughness_img, metallic_img))

    orm_path = None
    if basecolor:
        name = os.path.splitext(os.path.basename(basecolor))[0].split("_BaseColor")[0]
        orm_path = os.path.join(directory, f"{name}_Orm.png")
        orm_img.save(orm_path)
        if log:
            log.info(f"ORM: {os.path.basename(orm_path)}")
    elif log:
        log.warn("skip: BaseColor required to name ORM, ORM not created")

    return albedo_path, orm_path
