"""Helpers for `gleb glb` and the .glb-mode of `gleb compare`.

Wraps the gltf_import_inspect_probe and provides structural diff between
two inspect results.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gleb.core.blender_runner import run_blender_script
from gleb.core.exceptions import GlebError
from gleb.models.glb_schema import (
    GlbCompareData,
    GlbCompareMeta,
    GlbCompareResult,
    GlbCompareSummary,
    GlbInspect,
    GlbInspectData,
    GlbInspectMeta,
    GlbInspectResult,
    GlbInspectSummary,
    GlbObject,
    GlbObjectDiff,
    GlbPairDiff,
)

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "gleb" / "blender_scripts" / "gltf_import_inspect_probe.py"

GLB_SUFFIX = ".glb"


# ---------------------------------------------------------------------------
# Probe runner
# ---------------------------------------------------------------------------


def run_glb_inspect(
    paths: list[Path],
    blender_path: str | None = None,
    quiet: bool = True,
) -> GlbInspectResult:
    """Open one or more .glb files in a fresh Blender session and return a structured report.

    The probe imports each glb in order, collects per-object metadata (parent,
    UV layers, extras, material slots, polygon distribution per material slot)
    and clears the scene between files. Returns a Pydantic-validated envelope.
    """
    payload = {"glb_paths": [str(p.resolve()) for p in paths]}
    raw, version = run_blender_script(
        PROBE,
        payload,
        blender_path=blender_path,
        quiet=quiet,
    )

    data = raw.get("data") or {}
    imports = data.get("imports") or []
    inspects: list[GlbInspect] = []
    objects_total = 0
    files_failed = 0
    for entry in imports:
        if not isinstance(entry, dict):
            continue
        objs_raw = entry.get("objects") or []
        objects = [GlbObject.model_validate(o) for o in objs_raw if isinstance(o, dict)]
        ins = GlbInspect(
            path=str(entry.get("path", "")),
            import_failed=bool(entry.get("import_failed", False)),
            objects=objects,
        )
        if ins.import_failed:
            files_failed += 1
        objects_total += len(objects)
        inspects.append(ins)

    return GlbInspectResult(
        meta=GlbInspectMeta(blender_version=version, command="glb"),
        summary=GlbInspectSummary(
            files_inspected=len(inspects),
            files_failed=files_failed,
            objects_total=objects_total,
        ),
        data=GlbInspectData(inspects=inspects),
        warnings=list(raw.get("warnings") or []),
        errors=list(raw.get("errors") or []),
    )


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


# Object-level fields whose value changing flips the pair's `identical` bit.
# Extras are diffed as a single "extras" key (full dict comparison) to keep
# downstream output focused on structural changes rather than per-key noise.
_TRACKED_FIELDS: tuple[str, ...] = (
    "type",
    "parent",
    "vertices",
    "polygons",
    "uv_layers",
    "uv_layer_names",
    "uv2_island_overlaps",
    "uv0_sample",
    "extras",
    "material_slots",
    "polys_per_slot",
)


def _object_field_diffs(left: GlbObject, right: GlbObject) -> list[str]:
    changed: list[str] = []
    ld = left.model_dump()
    rd = right.model_dump()
    for f in _TRACKED_FIELDS:
        if ld.get(f) != rd.get(f):
            changed.append(f)
    return changed


def _diff_pair(
    name: str,
    left_inspect: GlbInspect,
    right_inspect: GlbInspect,
) -> GlbPairDiff:
    """Diff one paired (.glb, .glb) inspect result. Returns a structural diff."""
    if left_inspect.import_failed or right_inspect.import_failed:
        return GlbPairDiff(
            name=name,
            left_path=left_inspect.path,
            right_path=right_inspect.path,
            identical=False,
            object_count_left=len(left_inspect.objects),
            object_count_right=len(right_inspect.objects),
        )

    left_by = {o.name: o for o in left_inspect.objects}
    right_by = {o.name: o for o in right_inspect.objects}
    only_left = sorted(set(left_by) - set(right_by))
    only_right = sorted(set(right_by) - set(left_by))
    common = sorted(set(left_by) & set(right_by))

    obj_diffs: list[GlbObjectDiff] = []
    for n in common:
        lf = left_by[n]
        rt = right_by[n]
        fields = _object_field_diffs(lf, rt)
        if fields:
            ld = lf.model_dump()
            rd = rt.model_dump()
            obj_diffs.append(
                GlbObjectDiff(
                    name=n,
                    fields_changed=fields,
                    left={f: ld.get(f) for f in fields},
                    right={f: rd.get(f) for f in fields},
                )
            )

    identical = not only_left and not only_right and not obj_diffs

    return GlbPairDiff(
        name=name,
        left_path=left_inspect.path,
        right_path=right_inspect.path,
        identical=identical,
        object_count_left=len(left_inspect.objects),
        object_count_right=len(right_inspect.objects),
        objects_only_in_left=only_left,
        objects_only_in_right=only_right,
        object_diffs=obj_diffs,
    )


def _list_glbs(p: Path) -> list[Path]:
    return sorted(q for q in p.iterdir() if q.is_file() and q.suffix.lower() == GLB_SUFFIX)


def _resolve_pairs(left: Path, right: Path) -> tuple[list[tuple[str, Path, Path]], list[str], list[str]]:
    """Resolve `(name, left_path, right_path)` triples + names only-in-left / only-in-right."""
    if left.is_file() and right.is_file():
        return [(left.name, left, right)], [], []
    if left.is_dir() and right.is_dir():
        l_glbs = {p.name: p for p in _list_glbs(left)}
        r_glbs = {p.name: p for p in _list_glbs(right)}
        common = sorted(set(l_glbs) & set(r_glbs))
        only_l = sorted(set(l_glbs) - set(r_glbs))
        only_r = sorted(set(r_glbs) - set(l_glbs))
        return [(n, l_glbs[n], r_glbs[n]) for n in common], only_l, only_r
    raise GlebError(
        f"glb compare: both arguments must be .glb files OR both directories of .glb files; "
        f"got left={left} right={right}"
    )


def is_glb_compare_pair(left: Path, right: Path) -> bool:
    """True iff (left, right) should be routed to the .glb-pair compare path."""
    if left.is_file() and right.is_file():
        return left.suffix.lower() == GLB_SUFFIX and right.suffix.lower() == GLB_SUFFIX
    if left.is_dir() and right.is_dir():
        return any(_list_glbs(left)) and any(_list_glbs(right))
    return False


def run_glb_compare(
    left: Path,
    right: Path,
    blender_path: str | None = None,
    quiet: bool = True,
) -> GlbCompareResult:
    """Pair-and-diff two .glb files (or two directories of .glb files)."""
    pairs, only_left, only_right = _resolve_pairs(left, right)

    if not pairs:
        return GlbCompareResult(
            meta=GlbCompareMeta(left=str(left), right=str(right), identical=False),
            summary=GlbCompareSummary(
                pairs=0,
                pairs_identical=0,
                pairs_changed=0,
                pairs_only_in_left=only_left,
                pairs_only_in_right=only_right,
            ),
            warnings=["No paired .glb files to compare."] if not (only_left or only_right) else [],
            errors=[],
        )

    # Inspect everything in two single Blender processes to avoid spinning up
    # a fresh subprocess per file pair.
    left_paths = [lp for _, lp, _ in pairs]
    right_paths = [rp for _, _, rp in pairs]
    left_inspect = run_glb_inspect(left_paths, blender_path=blender_path, quiet=quiet)
    right_inspect = run_glb_inspect(right_paths, blender_path=blender_path, quiet=quiet)

    left_by_path = {Path(ins.path).name: ins for ins in left_inspect.data.inspects}
    right_by_path = {Path(ins.path).name: ins for ins in right_inspect.data.inspects}

    pair_diffs: list[GlbPairDiff] = []
    for name, lp, rp in pairs:
        l_ins = left_by_path.get(lp.name) or GlbInspect(path=str(lp), import_failed=True)
        r_ins = right_by_path.get(rp.name) or GlbInspect(path=str(rp), import_failed=True)
        pair_diffs.append(_diff_pair(name, l_ins, r_ins))

    n_identical = sum(1 for d in pair_diffs if d.identical)
    n_changed = len(pair_diffs) - n_identical
    overall_identical = (n_changed == 0) and not only_left and not only_right

    warnings: list[str] = []
    warnings.extend(f"left: {w}" for w in left_inspect.warnings)
    warnings.extend(f"right: {w}" for w in right_inspect.warnings)

    errors: list[str] = []
    errors.extend(f"left: {e}" for e in left_inspect.errors)
    errors.extend(f"right: {e}" for e in right_inspect.errors)

    return GlbCompareResult(
        meta=GlbCompareMeta(
            left=str(left),
            right=str(right),
            blender_version=left_inspect.meta.blender_version or right_inspect.meta.blender_version,
            identical=overall_identical,
        ),
        summary=GlbCompareSummary(
            pairs=len(pair_diffs),
            pairs_identical=n_identical,
            pairs_changed=n_changed,
            pairs_only_in_left=only_left,
            pairs_only_in_right=only_right,
        ),
        data=GlbCompareData(pairs=pair_diffs),
        warnings=warnings,
        errors=errors,
    )


def diff_summary_lines(result: GlbCompareResult, max_per_pair: int = 10) -> list[str]:
    """Compact text rendering of a GlbCompareResult — used by the pretty formatter and tests."""
    lines: list[str] = []
    lines.append(
        f"glb compare {result.meta.left} ↔ {result.meta.right}: "
        f"pairs={result.summary.pairs} identical={result.summary.pairs_identical} "
        f"changed={result.summary.pairs_changed}"
    )
    if result.summary.pairs_only_in_left:
        lines.append(f"  only in left: {result.summary.pairs_only_in_left}")
    if result.summary.pairs_only_in_right:
        lines.append(f"  only in right: {result.summary.pairs_only_in_right}")
    for pair in result.data.pairs:
        marker = "OK" if pair.identical else "CHG"
        lines.append(
            f"  [{marker}] {pair.name}  objects={pair.object_count_left}/{pair.object_count_right}"
        )
        if pair.objects_only_in_left:
            lines.append(f"      missing in right: {pair.objects_only_in_left[:max_per_pair]}")
        if pair.objects_only_in_right:
            lines.append(f"      extra in right:   {pair.objects_only_in_right[:max_per_pair]}")
        for d in pair.object_diffs[:max_per_pair]:
            lines.append(f"      ~ {d.name}: {d.fields_changed}")
    return lines


_INSPECTOR_FIELDS_PUBLIC: tuple[str, ...] = _TRACKED_FIELDS


def tracked_fields() -> tuple[str, ...]:
    """Return the list of object-level fields whose changes flip the diff bit (for tests/docs)."""
    return _INSPECTOR_FIELDS_PUBLIC
