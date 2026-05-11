# `gleb compare`

## Purpose

Compare two `.blend` files by running the same read-only **explore** probe on each file and diffing the structured `summary` and `data` sections. This is a **semantic** comparison of exported scene metadata — not a binary or datablock-level compare.

Left and right arguments follow **baseline vs candidate** ordering (same idea as `diff OLD NEW`).

## Usage

```bash
gleb compare <left.blend> <right.blend>
            [--scope SCOPE] [--object NAME]... [--match exact|contains|regex] [--ignore-case]
            [--detail] [--diagnose] [--pretty]
```

Options match **`gleb explore`** so both sides use identical scope, object filters, and verbosity.

## How it works

1. Runs **`gleb explore`** twice (via `run_explore`) with the same options on each file.
2. Compares **`summary`** and **`data`** from each JSON envelope only — probe **`meta`** paths are reported separately in `meta.left_file` / `meta.right_file` and are not treated as content differences.

List fields are compared **by index** (like positional diff). Reordering items in a list may therefore appear as edits even when the set of elements is unchanged.

## Output

Default: one JSON object to stdout with the usual gleb envelope keys:

- **`meta`** — `left_file`, `right_file`, both Blender versions, shared `scope` / `query`, `identical`.
- **`summary`** — `changed_paths` count and a flat `paths` list (dot-separated paths into the diff tree).
- **`data.changes`** — nested diff under `summary` and `explore_data` (each `null` when that subtree matches).
- **`warnings`** — left and right probe warnings, prefixed with `left:` / `right:`.
- **`errors`** — empty on success.

With **`--pretty`**, Rich renders trees for the diff plus a sample path table (first 200 paths).

## Exit codes

| Code | Meaning |
| ---- | ------- |
| `0`  | Both probes succeeded and **`summary` / `data` are structurally identical** for the chosen options. |
| `1`  | Validation or probe failure, non-empty probe `errors`, or **any** structural difference in `summary` / `data`. |

Useful for scripts: `gleb compare a.blend b.blend || echo "changed"`.

## Examples

```bash
gleb compare scene_v1.blend scene_v2.blend
gleb compare base.blend branch.blend --scope objects --pretty
gleb compare a.blend b.blend --scope materials --object Body --match contains
```

Blender is resolved like other commands: executable on `PATH` or **`BLENDER_PATH`**.
