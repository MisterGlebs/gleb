"""Write Godot .import stubs next to ORM textures after downscale."""

from __future__ import annotations

import os

from gleb.texture_pipeline.downscale import DOWNSCALE_SUBDIRS
from gleb.texture_pipeline.log import TextureLog

DEFAULT_PARAMS = """compress/mode=0
compress/high_quality=false
compress/lossy_quality=0.7
compress/uastc_level=0
compress/rdo_quality_loss=0.0
compress/hdr_compression=1
compress/normal_map=0
compress/channel_pack=0
mipmaps/generate=false
mipmaps/limit=-1
roughness/mode=0
roughness/src_normal=""
process/channel_remap/red=0
process/channel_remap/green=1
process/channel_remap/blue=2
process/channel_remap/alpha=3
process/fix_alpha_border=true
process/premult_alpha=false
process/normal_map_invert_y=false
process/hdr_as_srgb=false
process/hdr_clamp_exposure=false
process/size_limit=0
detect_3d/compress_to=1
"""


def _write_stub_with_res_path(image_path: str, res_source: str, *, params: str = DEFAULT_PARAMS) -> None:
    image_path = os.path.normpath(os.path.abspath(image_path))
    if not os.path.isfile(image_path):
        return
    basename = os.path.basename(image_path)
    placeholder_dest = f"res://.godot/imported/{basename}-00000000000000000000000000000000.ctex"
    res_source = res_source.rstrip("/")
    content = f"""[remap]

importer="texture"
type="CompressedTexture2D"
uid="uid://stub"
path="{placeholder_dest}"
metadata={{
"vram_texture": false
}}

[deps]

source_file="{res_source}/{basename}"
dest_files=["{placeholder_dest}"]

[params]

{params}
"""
    import_path = image_path + ".import"
    with open(import_path, "w", encoding="utf-8") as f:
        f.write(content)


def write_orm_import_stubs_for_downscale(
    downscale_dir: str, res_prefix: str, log: TextureLog | None = None
) -> int:
    """
    Find orig/half/quarter/eighth under downscale_dir; write .import for ORM-named textures.
    Returns number of stubs written.
    """
    downscale_dir = os.path.normpath(os.path.abspath(downscale_dir))
    res_prefix = res_prefix.rstrip("/")
    if not os.path.isdir(downscale_dir):
        raise FileNotFoundError(f"Not a directory: {downscale_dir}")

    count = 0
    for subdir in DOWNSCALE_SUBDIRS:
        subpath = os.path.join(downscale_dir, subdir)
        if not os.path.isdir(subpath):
            continue
        res_sub = f"{res_prefix}/{subdir}"
        for f in os.listdir(subpath):
            if not (f.lower().endswith(".png") or f.lower().endswith(".jpg")):
                continue
            if "_ORM" not in f and "_Orm" not in f and "_arm_" not in f.lower():
                continue
            img_path = os.path.join(subpath, f)
            if not os.path.isfile(img_path):
                continue
            _write_stub_with_res_path(img_path, res_sub)
            count += 1
            if log:
                log.info(f"{subdir}/{f}.import  ->  {res_prefix}/{subdir}/{f}")
    if log:
        log.info(f"Import stubs: {count} ORM textures (res prefix: {res_prefix})")
    return count
