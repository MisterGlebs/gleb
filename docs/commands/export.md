# `gleb export`

## Purpose

Export each **asset** (non-`_` root collection) from a `.blend` file as one `.glb`, matching `blender-godot-pipeline.md`.

Before export, objects receive glTF `extras` from collection membership:

| Path pattern | Stamped extras |
| ------------ | -------------- |
| `visual_<asset>/mesh_<asset>/layer_<N>_<asset>/` | `godot_type: mesh`, `render_layers` = `1 << (N-1)` |
| `visual_<asset>/multimesh_<asset>/layer_<N>_<asset>/` | same as mesh (MultiMesh baking in Godot is future) |
| `static_<asset>/trimesh_<asset>/tri_layer_<N>_<asset>/` | `godot_type: collision_trimesh`, `collision_layer` = `1 << (N-1)`, `collision_mask: 0` |
| `static_<asset>/convex_<asset>/cvx_layer_<N>_<asset>/` | `godot_type: collision_convex`, same layer fields |
| `static_<asset>/box_<asset>/box_layer_<N>_<asset>/` | `godot_type: collision_box`, same layer fields |

**Legacy patterns** (older blends): plain `layer_<N>`, `tri_layer_<N>`, `cvx_layer_<N>`, `box_layer_<N>` (optional `.###` suffix).

Per-object custom properties already set are **not** overwritten.

Root collections whose name starts with `_` are **skipped** entirely.

## Usage

```bash
gleb export <file.blend> [--output-dir DIR] [--asset NAME]... [--pretty] [--quiet] [--blender PATH]
```

## Arguments

| Argument      | Description |
| ------------- | ----------- |
| `file.blend`  | Source file opened by Blender. |

## Options

| Option              | Description |
| ------------------- | ----------- |
| `--output-dir DIR`  | Output directory (created if missing). Default: `<blend_dir>/export/`. |
| `--asset NAME`      | Export only this root asset (repeatable). Omit = all non-`_` roots. |
| `--pretty`          | Rich output instead of JSON. |
| `--quiet`           | Suppress Blender stderr. |
| `--blender PATH`    | Blender 5+ executable. |

## glTF / `.glb` export settings (Blender)

`gleb export` calls `bpy.ops.export_scene.gltf` with:

| Setting | Default | Notes |
| ------- | ------- | ----- |
| **Apply modifiers** | on (`export_apply=True`) | Bakes Subdivision, Mirror, Bevel, etc. Armature is still handled for skinning. **Off** with `--no-apply-modifiers` (needed if you rely on **shape keys** — applying modifiers drops them). |
| **Tangents** | on (`export_tangents=True`) | Blends default is off; **on** is better for normal-mapped PBR in Godot. `--no-export-tangents` to match old behavior. |
| **Materials** | `EXPORT` | Full glTF PBR from Principled BSDF / glTF-compatible nodes. **Recommended for the GlbSceneBuilder pipeline** — preserves Blender material names as `resource_name` on imported surfaces, enabling `auto_resolve_materials` name-based lookup in Godot. `--materials PLACEHOLDER` strips names (avoid unless you never use `auto_resolve_materials`). `VIEWPORT` / `NONE` are rare. |
| **UVs / normals** | on | `export_texcoords`, `export_normals` |
| **Custom properties → extras** | on | Required for `godot_type` / layer metadata. |
| **+Y up** | on | Matches glTF; Godot import handles orientation. |
| **Animations** | on | NLA / actions included when present. |

Complex procedural materials may still need baking or replacement in Godot — same as a manual Blender glTF export.

## Collection walk (summary)

Under each asset:

- Children whose names **start with** `visual` → children **`mesh_*`** or **`multimesh_*`** → **`layer_<N>_*`** folders.
- Children whose names **start with** `static` → children **`trimesh_*`**, **`convex_*`**, **`box_*`** → **`tri_layer_*`**, **`cvx_layer_*`**, **`box_layer_*`** folders respectively.

## Output

`summary`: `assets_exported`, `assets_skipped`, `assets_failed`.

`data`: `output_dir`, `exports` — each `{ asset, path, status }`.

## Warnings

Objects linked only to the asset root (outside the pipeline layer folders above) trigger a warning; they still export in the `.glb` but do not receive automatic extras.

## Examples

```bash
# Standard pipeline export (material names preserved — required for auto_resolve_materials)
gleb export level.blend

# Export to specific directory
gleb export level.blend --output-dir ./out --asset north_facade

# Multiple assets, readable output
gleb export level.blend --asset a --asset b --pretty
```
