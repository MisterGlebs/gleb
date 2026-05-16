# `gleb glb`

## Purpose

Inspect the `.glb` files produced by **`gleb export`** in a fresh Blender session. The output describes exactly what Godot will see when it imports the file — per-object metadata, glTF extras, UV layer state, material slots, and polygon distribution per material slot.

This is the host-side counterpart of **`gleb explore`** (which inspects `.blend` source). Use `gleb glb show` to look at a single export, and `gleb compare` (auto-routes when given `.glb` files / dirs) to diff two exports.

## Usage

```bash
gleb glb show <file.glb> [<file2.glb> ...] [--pretty] [--quiet/--verbose]
```

Each `.glb` is imported into a fresh, empty scene; the scene is cleared between files. Importing happens in a single Blender background process for all listed files (one subprocess, not one per file).

## Output

JSON envelope `{meta, summary, data, warnings, errors}` with these fields:

- **`meta`** — `blender_version`, `command: "glb"`.
- **`summary`** — `files_inspected`, `files_failed`, `objects_total`.
- **`data.inspects`** — list of `{path, import_failed, objects[]}`.

Each entry in `objects[]` carries:

| field | type | meaning |
| ----- | ---- | ------- |
| `name` | string | Object name as imported (matches the source `.blend` exactly when `gleb export --bake-uv2` is used; the bake suffix is stripped before export). |
| `type` | string | Blender object type (`MESH`, `EMPTY`, ...). |
| `parent` | string \| null | Parent object name, or `null` if root. Catches parent-orphan drops in the bake pipeline. |
| `vertices` | int | After modifier evaluation. |
| `polygons` | int | After modifier evaluation. |
| `extras` | object | glTF `extras` stamped by `gleb export` (e.g. `godot_type`, `render_layers`, `lightmap_texel_size`). |
| `uv_layers` | int | UV layer count. `1` for unbaked, `2` after `--bake-uv2`. |
| `uv_layer_names` | string[] | Layer names in slot order (note: glTF strips these in transit; expect generic names). |
| `uv2_island_overlaps` | bool | Union-find AABB check on `TEXCOORD_1`. `True` ⇒ Array/Mirror copies share lightmap texels. |
| `uv0_sample` | [float, float] \| null | UV0 of the first loop. Used as a sentinel to verify TEXCOORD_0 stayed render-active across the bake. |
| `material_slots` | object[] | One entry per slot: `{link, material: {name, blend_method, base_color_default, base_color_linked_from, alpha_default, alpha_linked_from, principled_present, metallic, roughness, use_backface_culling, ...} \| null}`. |
| `polys_per_slot` | object | Map `slot_index_str → polygon_count`. The slot indices that actually back geometry — a `material_slots` entry with no key here is unused by polygons. |

With `--pretty` the same data is rendered as a Rich table per file.

## Why these fields

This is the exact set the diagnostic scripts in the original `bake-uv2` investigation needed to triangulate the bug:

- **Missing meshes after bake** ⇒ object name absent from one side ⇒ visible immediately as `objects_only_in_*` in `gleb compare`.
- **Suffix leak in node names** (`__uv2bake`) ⇒ visible as `objects_only_in_right` (different basename).
- **Material slot or first-slot transparency in Godot** ⇒ `material_slots` and `polys_per_slot` differences flagged per-mesh.
- **TEXCOORD_0 / TEXCOORD_1 swap** ⇒ `uv_layers` count or `uv0_sample` change.
- **Lightmap-texel drift** ⇒ `extras.lightmap_texel_size` mismatch.

## Diff

There is no `gleb glb diff` subcommand on purpose — the diff side of this is folded into **`gleb compare`**, which auto-routes to glb-pair mode when both arguments are `.glb` files (or both are directories of `.glb` files). See `docs/commands/compare.md`.

## Exit codes

| Code | Meaning |
| ---- | ------- |
| `0`  | All files imported and reported. |
| `1`  | Missing file, non-`.glb` argument, or Blender failure. Per-file import failures populate `data.inspects[i].import_failed = true` but **do not** fail the command (so you still get the partial report). |

## Examples

```bash
# JSON envelope (machine-friendly)
gleb glb show exports/level.glb > inspect.json

# Rich table view of every imported asset in a directory
gleb glb show exports/*.glb --pretty

# Pair with a real diff
gleb compare exports/baseline/level.glb exports/candidate/level.glb --pretty
```

Blender is resolved like other commands: executable on `PATH` or **`BLENDER_PATH`**.
