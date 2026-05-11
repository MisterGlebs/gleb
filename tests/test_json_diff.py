from __future__ import annotations

from gleb.core.json_diff import (
    LEAF,
    ONLY_LEFT,
    ONLY_RIGHT,
    count_diff_nodes,
    diff_any,
    flatten_diff_paths,
)


def test_diff_any_identical() -> None:
    assert diff_any({"a": 1}, {"a": 1}) is None
    assert diff_any([1, 2], [1, 2]) is None


def test_diff_scalar_mismatch() -> None:
    d = diff_any({"x": 1}, {"x": 2})
    assert d == {"x": {LEAF: {"left": 1, "right": 2}}}


def test_diff_dict_key_added_removed() -> None:
    d = diff_any({"a": 1}, {"b": 2})
    assert "a" in d
    assert ONLY_LEFT in d["a"]
    assert "b" in d
    assert ONLY_RIGHT in d["b"]


def test_diff_list_length_and_items() -> None:
    d = diff_any([1], [1, 2])
    assert d is not None
    assert ONLY_RIGHT in d["1"]
    assert d["1"][ONLY_RIGHT] == 2


def test_diff_type_mismatch() -> None:
    d = diff_any({"k": []}, {"k": {}})
    assert d is not None
    assert LEAF in d["k"]


def test_flatten_paths_and_count() -> None:
    left = {"summary": {"objects": 1}, "data": {"scene": {"name": "A"}}}
    right = {"summary": {"objects": 2}, "data": {"scene": {"name": "A"}}}
    sd = diff_any(left["summary"], right["summary"])
    dd = diff_any(left["data"], right["data"])
    assert sd is not None
    paths = flatten_diff_paths(sd, "summary") + flatten_diff_paths(dd, "explore_data")
    assert "summary.objects" in paths
    assert count_diff_nodes(sd) >= 1
