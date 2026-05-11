"""Structural JSON-like diff for explore payloads (no third-party deps)."""

from __future__ import annotations

from typing import Any

# Sentinels inside diff trees (unlikely to collide with Blender/export keys).
LEAF = "__gleb_leaf__"
ONLY_LEFT = "__gleb_only_left__"
ONLY_RIGHT = "__gleb_only_right__"


def diff_any(left: Any, right: Any) -> Any | None:
    """Return None if structurally equal; otherwise a nested diff tree."""
    if left == right:
        return None
    if type(left) is not type(right):
        return {LEAF: {"left": left, "right": right}}

    if isinstance(left, dict):
        return _diff_dict(left, right)
    if isinstance(left, list):
        return _diff_list(left, right)

    return {LEAF: {"left": left, "right": right}}


def _diff_dict(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any] | None:
    out: dict[str, Any] = {}
    keys_a = set(a.keys())
    keys_b = set(b.keys())
    for k in sorted(keys_a - keys_b):
        out[k] = {ONLY_LEFT: a[k]}
    for k in sorted(keys_b - keys_a):
        out[k] = {ONLY_RIGHT: b[k]}
    for k in sorted(keys_a & keys_b):
        sub = diff_any(a[k], b[k])
        if sub is not None:
            out[k] = sub
    return out if out else None


def _diff_list(a: list[Any], b: list[Any]) -> dict[str, Any] | None:
    if a == b:
        return None
    out: dict[str, Any] = {}
    n, m = len(a), len(b)
    for i in range(max(n, m)):
        key = str(i)
        if i >= n:
            out[key] = {ONLY_RIGHT: b[i]}
        elif i >= m:
            out[key] = {ONLY_LEFT: a[i]}
        else:
            sub = diff_any(a[i], b[i])
            if sub is not None:
                out[key] = sub
    return out if out else None


def count_diff_nodes(tree: Any) -> int:
    """Count leaf change records (scalar mismatches, only_left, only_right)."""
    if tree is None:
        return 0
    if isinstance(tree, dict):
        if LEAF in tree or ONLY_LEFT in tree or ONLY_RIGHT in tree:
            return 1
        return sum(count_diff_nodes(v) for v in tree.values())
    if isinstance(tree, list):
        return sum(count_diff_nodes(item) for item in tree)
    return 0


def flatten_diff_paths(tree: Any, prefix: str = "") -> list[str]:
    """Collect dot-separated paths to leaf changes (for pretty / stats)."""
    paths: list[str] = []
    if tree is None:
        return paths
    if isinstance(tree, dict):
        if LEAF in tree or ONLY_LEFT in tree or ONLY_RIGHT in tree:
            paths.append(prefix or ".")
            return paths
        for k, v in tree.items():
            seg = k if not prefix else f"{prefix}.{k}"
            paths.extend(flatten_diff_paths(v, seg))
        return paths
    if isinstance(tree, list):
        for i, item in enumerate(tree):
            seg = f"{prefix}.{i}" if prefix else str(i)
            paths.extend(flatten_diff_paths(item, seg))
    return paths
