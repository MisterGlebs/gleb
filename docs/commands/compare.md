# `gleb compare`

## Purpose

Compare two artifacts by running the relevant read-only probe on each side and diffing the structured `summary` and `data` sections. This is a **semantic** comparison — not a binary or datablock-level compare.

Three input modes are auto-detected from the argument types:

| Left arg | Right arg | Mode |
| -------- | --------- | ---- |
| `*.blend` | `*.blend` | **blend ↔ blend** (explore probe + structural diff) |
| `*.glb`   | `*.glb`   | **glb ↔ glb** (single-pair `gleb glb` inspect on both, then diff) |
| directory | directory | **glb dir ↔ glb dir** (pair `.glb` files by basename, diff each pair) |

Mixing `.blend` with `.glb` is rejected. Left/right arguments follow **baseline vs candidate** ordering (same idea as `diff OLD NEW`).

## Usage

```bash
# blend ↔ blend (existing behavior)
gleb compare <left.blend> <right.blend>
            [--scope SCOPE] [--object NAME]... [--match exact|contains|regex] [--ignore-case]
            [--detail] [--diagnose] [--pretty]

# glb ↔ glb
gleb compare <left.glb> <right.glb> [--pretty]

# directory of .glb files ↔ directory of .glb files
gleb compare <left_dir>/ <right_dir>/ [--pretty]
```

The `--scope` / `--object` / `--match` / `--ignore-case` / `--detail` / `--diagnose` options apply to **blend ↔ blend** mode only and match the corresponding **`gleb explore`** options. They are ignored in glb modes.

## How it works

1. Runs **`gleb explore`** twice (via `run_explore`) with the same options on each file.
2. Compares **`summary`** and **`data`** from each JSON envelope only — probe **`meta`** paths are reported separately in `meta.left_file` / `meta.right_file` and are not treated as content differences.

List fields are compared **by index** (like positional diff). Reordering items in a list may therefore appear as edits even when the set of elements is unchanged.

## Output

### blend ↔ blend

Default: one JSON object to stdout with the usual gleb envelope keys:

- **`meta`** — `left_file`, `right_file`, both Blender versions, shared `scope` / `query`, `identical`.
- **`summary`** — `changed_paths` count and a flat `paths` list (dot-separated paths into the diff tree).
- **`data.changes`** — nested diff under `summary` and `explore_data` (each `null` when that subtree matches).
- **`warnings`** — left and right probe warnings, prefixed with `left:` / `right:`.
- **`errors`** — empty on success.

With **`--pretty`**, Rich renders trees for the diff plus a sample path table (first 200 paths).

### glb ↔ glb / glb dir ↔ glb dir

Same envelope but the schema is **`GlbCompareResult`** (see `docs/commands/glb.md`):

- **`meta`** — `left`, `right`, `blender_version`, `identical`.
- **`summary`** — `pairs`, `pairs_identical`, `pairs_changed`, plus `pairs_only_in_left` / `pairs_only_in_right` (in dir-pair mode, basenames present on only one side).
- **`data.pairs`** — list of `GlbPairDiff`. Each pair carries: `name`, `left_path`, `right_path`, `identical`, `object_count_left/right`, `objects_only_in_left/right`, and `object_diffs` (per-mesh `fields_changed` from a fixed tracked-fields set: `type`, `parent`, `vertices`, `polygons`, `uv_layers`, `uv_layer_names`, `uv2_island_overlaps`, `uv0_sample`, `extras`, `material_slots`, `polys_per_slot`).

The diff catches every class of regression I've personally hit on the `bake-uv2` flow: missing meshes (parent-orphan drop), suffix leak in node names, UV layer count or names changing, extras drift, material-slot rewiring (which in Godot manifests as transparent first surface), polygons re-routed across slots.

## Exit codes

| Code | Meaning |
| ---- | ------- |
| `0`  | Both sides succeeded **and** are structurally identical. |
| `1`  | Validation or probe failure, non-empty probe `errors`, OR **any** structural difference. |

Useful for scripts: `gleb compare baseline/ candidate/ || echo "changed"`.

## Examples

```bash
# blend ↔ blend
gleb compare scene_v1.blend scene_v2.blend
gleb compare base.blend branch.blend --scope objects --pretty
gleb compare a.blend b.blend --scope materials --object Body --match contains

# glb ↔ glb (find the parented-orphan / material drop after a bake change)
gleb compare exports/no_uv2/level.glb exports/with_uv2/level.glb --pretty

# glb dir ↔ glb dir (diff every paired asset between two export runs)
gleb compare exports/baseline exports/candidate --pretty
```

Blender is resolved like other commands: executable on `PATH` or **`BLENDER_PATH`**.
