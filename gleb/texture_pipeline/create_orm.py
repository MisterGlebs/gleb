"""Create Godot-style ORM textures from separate AO / Roughness / Metallic maps."""

from __future__ import annotations

import os
import re
from pathlib import Path

import numpy as np
from PIL import Image

from gleb.texture_pipeline.log import TextureLog

try:
    import cv2  # type: ignore[import-untyped]

    _EXR_AVAILABLE = getattr(cv2, "imread", None) is not None
except ImportError:
    _EXR_AVAILABLE = False
if not _EXR_AVAILABLE:
    try:
        import imageio  # type: ignore[import-untyped]

        _EXR_AVAILABLE = True
    except ImportError:
        pass

CH_R = 0
CH_G = 1
CH_B = 2

FILL_NO_AO = 255
FILL_NO_ROUGHNESS = 128
FILL_NO_METALNESS = 0


def _is_image_ext(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in (".png", ".jpg", ".jpeg", ".exr")


def _list_images(directory: str) -> list[str]:
    return [
        f
        for f in os.listdir(directory)
        if _is_image_ext(f) and os.path.isfile(os.path.join(directory, f))
    ]


def _read_grayscale_float(path: str, log: TextureLog | None) -> np.ndarray | None:
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".exr":
            if not _EXR_AVAILABLE:
                if log:
                    log.warn(
                        f"EXR not supported (install opencv-python or imageio), skip: "
                        f"{os.path.basename(path)}"
                    )
                return None
            try:
                import cv2 as _cv2

                arr = _cv2.imread(path, _cv2.IMREAD_ANYDEPTH | _cv2.IMREAD_ANYCOLOR)
            except Exception:
                import imageio as _imageio

                arr = _imageio.imread(path)
            if arr is None:
                return None
            if arr.ndim == 3:
                arr = arr[:, :, 0]
            if arr.dtype.kind == "f":
                arr = np.clip(arr, 0.0, 1.0)
            else:
                arr = arr.astype(np.float64) / np.iinfo(arr.dtype).max
            return np.clip(arr, 0.0, 1.0)
        img = Image.open(path)
        if img.mode != "L":
            img = img.convert("L")
        arr = np.array(img, dtype=np.float64) / 255.0
        return np.clip(arr, 0.0, 1.0)
    except Exception as e:
        if log:
            log.warn(f"failed to read {os.path.basename(path)}: {e}")
        return None


def _float_to_uint8(arr: np.ndarray) -> np.ndarray:
    return (np.clip(arr, 0.0, 1.0) * 255.0).astype(np.uint8)


def _resize_to(arr: np.ndarray, width: int, height: int) -> np.ndarray:
    if arr.shape[1] == width and arr.shape[0] == height:
        return arr
    pil = Image.fromarray((np.clip(arr, 0.0, 1.0) * 255.0).astype(np.uint8))
    pil = pil.resize((width, height), Image.Resampling.LANCZOS)
    return np.array(pil, dtype=np.float64) / 255.0


def _detect_convention(files: list[str]) -> str:
    bases = [os.path.splitext(f)[0].lower() for f in files]
    if any(
        b.endswith("_ao") or b.endswith("_roughness") or b.endswith("_metalness") for b in bases
    ):
        return "fab"
    lower = [f.lower() for f in files]
    if any("_arm_" in f for f in lower):
        return "polyhaven"
    if any("_ao_" in f or "_rough_" in f or "_metal_" in f for f in lower):
        return "polyhaven"
    return "unknown"


def _find_fab_maps(
    directory: str, files: list[str]
) -> tuple[str | None, str | None, str | None]:
    ao = rough = metal = None
    for f in files:
        if not _is_image_ext(f):
            continue
        fp = os.path.join(directory, f)
        base = os.path.splitext(f)[0].lower()
        if base.endswith("_ao"):
            ao = fp
        elif base.endswith("_roughness"):
            rough = fp
        elif base.endswith("_metalness"):
            metal = fp
    return (ao, rough, metal)


def _find_polyhaven_maps(
    directory: str, files: list[str]
) -> tuple[str | None, str | None, str | None]:
    def by_pattern(suffix: str) -> list[str]:
        out = []
        for f in files:
            if suffix in f.lower() and _is_image_ext(f):
                out.append(f)
        pngs = [x for x in out if x.lower().endswith(".png")]
        if pngs:
            return pngs
        return out

    ao_list = by_pattern("_ao_")
    rough_list = by_pattern("_rough_")
    metal_list = by_pattern("_metal_")

    def pick_one(paths: list[str]) -> str | None:
        if not paths:
            return None
        return os.path.join(directory, paths[0])

    return (pick_one(ao_list), pick_one(rough_list), pick_one(metal_list))


def _has_polyhaven_arm(files: list[str]) -> bool:
    return any("_arm_" in f.lower() for f in files)


def _convert_normal_exr_to_png(directory: str, files: list[str], log: TextureLog | None) -> None:
    for f in files:
        if "_nor_" not in f.lower():
            continue
        if not f.lower().endswith(".exr"):
            continue
        path = os.path.join(directory, f)
        out_path = os.path.join(directory, os.path.splitext(f)[0] + ".png")
        if os.path.exists(out_path):
            if log:
                log.info(f"skip: normal PNG already exists: {os.path.basename(out_path)}")
            continue
        try:
            used_cv2 = False
            if _EXR_AVAILABLE:
                try:
                    import cv2 as _cv2

                    arr = _cv2.imread(path, _cv2.IMREAD_ANYDEPTH | _cv2.IMREAD_ANYCOLOR)
                    used_cv2 = arr is not None
                except Exception:
                    arr = None
                if arr is None:
                    try:
                        import imageio as _imageio

                        arr = _imageio.imread(path)
                    except Exception:
                        pass
            else:
                if log:
                    log.warn(f"EXR not supported, cannot convert normal: {os.path.basename(path)}")
                continue
            if arr is None:
                if log:
                    log.warn(f"could not read EXR: {os.path.basename(path)}")
                continue
            if arr.ndim == 3 and arr.shape[2] >= 3 and used_cv2:
                arr = arr[:, :, ::-1]
            if arr.dtype.kind == "f":
                arr = np.clip(arr, 0.0, 1.0)
            else:
                arr = arr.astype(np.float64) / np.iinfo(arr.dtype).max
            arr_u8 = (np.clip(arr, 0.0, 1.0) * 255.0).astype(np.uint8)
            if arr_u8.ndim == 2:
                img = Image.fromarray(arr_u8, mode="L")
            else:
                img = Image.fromarray(arr_u8[:, :, :3].copy(), mode="RGB")
            img.save(out_path)
            if log:
                log.info(f"normal EXR -> PNG: {f} -> {os.path.basename(out_path)}")
        except Exception as e:
            if log:
                log.warn(f"failed to convert normal EXR {os.path.basename(path)}: {e}")


def _base_name_from_path(path: str | None, convention: str) -> str:
    if path:
        name = os.path.splitext(os.path.basename(path))[0]
        if convention == "fab":
            for suffix in ("_AO", "_Roughness", "_Metalness", "_ao", "_Roughness", "_Metalness"):
                if suffix in name:
                    return name.split(suffix)[0].rstrip("_")
        if convention == "polyhaven":
            for part in ("_ao_", "_rough_", "_metal_", "_arm_"):
                if part in name.lower():
                    return re.sub(r"(_ao_|_rough_|_metal_|_arm_).*", "", name, flags=re.I).rstrip(
                        "_"
                    )
        return name
    return "material"


def _merge_channels_to_orm(
    ao_path: str | None,
    rough_path: str | None,
    metal_path: str | None,
    convention: str,
    log: TextureLog | None,
) -> tuple[np.ndarray, int, int]:
    """Build RGB uint8 ORM array and output dimensions."""
    w_max, h_max = 0, 0
    sources: list[tuple[np.ndarray | None, int | None, str]] = []

    for path, fill_uint8, label in [
        (ao_path, FILL_NO_AO, "AO"),
        (rough_path, FILL_NO_ROUGHNESS, "Roughness"),
        (metal_path, FILL_NO_METALNESS, "Metallic"),
    ]:
        if path:
            arr = _read_grayscale_float(path, log)
            if arr is not None:
                h, w = arr.shape[:2]
                w_max = max(w_max, w)
                h_max = max(h_max, h)
                sources.append((arr, None, label))
            else:
                sources.append((None, fill_uint8, label))
        else:
            sources.append((None, fill_uint8, label))

    if w_max == 0 or h_max == 0:
        w_max = 1024
        h_max = 1024
        if log:
            log.info("size: 1024x1024 (default, no valid map)")
    elif log:
        log.info(f"size: {w_max}x{h_max} (max of inputs, others stretched to fit)")

    r_ch = np.full((h_max, w_max), FILL_NO_AO / 255.0, dtype=np.float64)
    g_ch = np.full((h_max, w_max), FILL_NO_ROUGHNESS / 255.0, dtype=np.float64)
    b_ch = np.full((h_max, w_max), FILL_NO_METALNESS / 255.0, dtype=np.float64)

    for i, (arr, fill, label) in enumerate(sources):
        if arr is not None:
            arr = _resize_to(arr, w_max, h_max)
            if i == CH_R:
                r_ch = arr
            elif i == CH_G:
                g_ch = arr
            else:
                b_ch = arr
            if log:
                log.info(f"  {label}: from texture (resized to {w_max}x{h_max})")
        else:
            if log:
                log.info(f"  {label}: default ({fill}/255)")

    r_u8 = _float_to_uint8(r_ch)
    g_u8 = _float_to_uint8(g_ch)
    b_u8 = _float_to_uint8(b_ch)
    orm = np.stack([r_u8, g_u8, b_u8], axis=-1)
    return orm, w_max, h_max


def create_orm_from_paths(
    *,
    output_path: str | Path,
    ao_path: str | None = None,
    roughness_path: str | None = None,
    metallic_path: str | None = None,
    log: TextureLog | None = None,
) -> tuple[str, int, int]:
    """
    Write a single ORM PNG from explicit map paths (Godot R=AO, G=roughness, B=metallic).
    Missing channels use FILL_* defaults. At least one input path should exist for sensible size;
    otherwise output is 1024x1024.
    """
    out = os.path.normpath(os.path.abspath(str(output_path)))
    parent = os.path.dirname(out)
    os.makedirs(parent, exist_ok=True)

    if ao_path is None and roughness_path is None and metallic_path is None:
        raise ValueError("At least one of --ao, --roughness, --metallic must be provided")

    for p in (ao_path, roughness_path, metallic_path):
        if p is not None and not os.path.isfile(p):
            raise FileNotFoundError(f"Not a file: {p}")

    orm_arr, w_max, h_max = _merge_channels_to_orm(
        ao_path, roughness_path, metallic_path, "manual", log
    )
    pil_orm = Image.fromarray(orm_arr, mode="RGB")
    pil_orm.save(out)
    if log:
        log.info(f"saved: {os.path.basename(out)}")
    return out, w_max, h_max


def create_orm_for_directory(directory: str, log: TextureLog | None = None) -> str | None:
    """Create ORM PNG in ``directory`` using FAB/Polyhaven naming. Returns output path or None."""
    directory = os.path.abspath(directory)
    if not os.path.isdir(directory):
        if log:
            log.warn(f"not a directory: {directory}")
        return None

    files = _list_images(directory)
    if not files:
        if log:
            log.info(f"Skip: no images in directory: {directory}")
        return None

    convention = _detect_convention(files)
    if log:
        log.info(f"convention: {convention}")

    if convention == "polyhaven":
        _convert_normal_exr_to_png(directory, files, log)

    if convention == "polyhaven" and _has_polyhaven_arm(files):
        if log:
            log.info("skip: existing *_arm_* ORM found, no ORM created")
        return None

    if convention == "fab":
        ao_path, rough_path, metal_path = _find_fab_maps(directory, files)
    elif convention == "polyhaven":
        ao_path, rough_path, metal_path = _find_polyhaven_maps(directory, files)
    else:
        ao_path, rough_path, metal_path = _find_fab_maps(directory, files)
        if ao_path or rough_path or metal_path:
            convention = "fab"
        else:
            ao_path, rough_path, metal_path = _find_polyhaven_maps(directory, files)
            convention = "polyhaven"

    if log:
        ao_b = os.path.basename(ao_path) if ao_path else "none"
        rough_b = os.path.basename(rough_path) if rough_path else "none"
        metal_b = os.path.basename(metal_path) if metal_path else "none"
        log.info(f"maps: AO={ao_b}  Roughness={rough_b}  Metalness={metal_b}")

    orm_arr, _, _ = _merge_channels_to_orm(ao_path, rough_path, metal_path, convention, log)
    pil_orm = Image.fromarray(orm_arr, mode="RGB")

    base_name = _base_name_from_path(ao_path or rough_path or metal_path, convention)
    out_path = os.path.join(directory, f"{base_name}_ORM.png")
    pil_orm.save(out_path)
    if log:
        log.info(f"saved: {os.path.basename(out_path)}")
    return out_path
