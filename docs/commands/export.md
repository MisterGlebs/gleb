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
| `--bake-uv2 / --no-bake-uv2` | Bake a second UV layer (TEXCOORD_1) inside Blender for Godot LightmapGI. Default off. See "UV2 baking" below. |
| `--uv2-method [smart\|lightmap_pack]` | Unwrap operator. Default `smart`. |
| `--uv2-margin FLOAT` | Island margin in UV space. Default `0.02`. |
| `--target-texel-density FLOAT` | Lightmap texels per world meter (`lightmap_texel_size = 1 / density`). Default `4.0` -> `0.25`. |
| `--write-import-sidecar` | Write a Godot `<asset>.glb.import` next to each `.glb`. Off by default; only writes if the file does not already exist. |
| `--lightmap-texel-density-prop NAME` | Custom-property name read from each asset root collection to override `--target-texel-density` per asset. Default `lightmap_texel_density`. |

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

`data`: `output_dir`, `exports` — each `{ asset, path, status, uv2_baked_meshes, uv2_skipped_meshes, lightmap_texel_size, sidecar_path }`. The last four are populated only under `--bake-uv2` / `--write-import-sidecar`.

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

# Bake UV2 + write Godot import sidecar (recommended for LightmapGI)
gleb export level.blend --bake-uv2 --target-texel-density 4 --write-import-sidecar
```

## UV2 baking

`--bake-uv2` makes `gleb export` produce **TEXCOORD_1** for every visual mesh inside the `.glb` so Godot's LightmapGI baker uses the Blender-side unwrap and **never** falls back to its built-in xatlas pass. xatlas is the source of the well-known "black box / transparent garbage" artifacts on some meshes; pre-baked UV2 sidesteps the bug entirely.

### What runs per visual mesh

For every `MESH` object under `visual_<asset>/(mesh|multimesh)_<asset>/layer_*/`:

1. **Modifier-bake first.** A duplicate of the object is created in place via `obj.evaluated_get(depsgraph)` + `bpy.data.meshes.new_from_object(...)`. All modifiers (Subdivision, Array, Mirror, Bevel, ...) are applied into a fresh mesh datablock. The duplicate is swapped into the asset's collection in place of the original; the original is unlinked. **Required**: a naive "unwrap then let glTF apply Array" yields one shared UV island for all Array copies.
2. **Add UV2 layer.** A second UV layer is appended; UV0 stays render-active so glTF emits the original UV as `TEXCOORD_0` and the new layer as `TEXCOORD_1`.
3. **Unwrap.** `bpy.ops.uv.smart_project` (or `lightmap_pack`) -> `bpy.ops.uv.average_islands_scale` (equalizes texels per 3D area within the mesh) -> `bpy.ops.uv.pack_islands`.
4. **Per-component grid pack.** A deterministic pass walks vertex-connected components and lays each into its own grid cell of `[0, 1]`. Required because Blender's unwrap operators **deduplicate identical-geometry components** (Array / Mirror copies) and stack their UV islands on top of each other; the grid pack guarantees one UV slot per copy.
5. **Stamp `lightmap_texel_size`** as a custom property on the duplicate (visible as a glTF `extra` on the imported `MeshInstance3D`).
6. **glTF export** with `export_apply=False` (modifiers already applied).
7. **Restore.** In `try / finally` the duplicate is unlinked, the original is relinked, and the duplicate's mesh datablock is removed. The source `.blend` is byte-identical before and after. Tested in `tests/test_export_uv2.py::test_uv2_source_blend_byte_identical`.

Collision meshes under `static_*` are deliberately untouched.

If a mesh already has 2 or more UV layers, the unwrap is **skipped** and a warning is emitted (honor pre-baked work).

### Texel density

```
lightmap_texel_size = 1 / target_texel_density
```

For example `--target-texel-density 4` -> `lightmap_texel_size = 0.25` (1 lightmap texel per 0.25 world meters, i.e. 4 texels per meter).

Per-asset override: tag the asset's root Collection with a custom property whose name matches `--lightmap-texel-density-prop` (default `lightmap_texel_density`):

```
fac_a:                                 # asset root collection
  custom prop "lightmap_texel_density" = 8.0   # higher detail than the CLI default
```

In Blender: select the collection in the Outliner, Object Data Properties is per-object; for collection custom properties use the Outliner's "..." menu -> "Properties" or set in script.

### Godot import settings (`--write-import-sidecar`)

When `--write-import-sidecar` is passed, `gleb export` writes `<asset>.glb.import` next to each `.glb`:

```ini
[remap]
importer="scene"
type="PackedScene"

[params]
meshes/light_baking=2                 # Static Lightmaps
meshes/lightmap_texel_size=<1/density>
meshes/generate_lods=true
meshes/create_shadow_meshes=true
nodes/use_node_type_suffixes=false
```

Behavior:

- **Write-only-if-missing.** Existing `.glb.import` files are NEVER overwritten; a warning is emitted naming the preserved file.
- To refresh after changing `--target-texel-density`, delete the `.glb.import` first.
- Without the sidecar, you must flip Godot's import-dock settings manually once per asset (set Light Baking to "Static Lightmaps" and configure Lightmap Texel Size).

After import, place a `LightmapGI` node and Bake. UV2 ships from the `.glb` (`TEXCOORD_1`), so xatlas never runs.
