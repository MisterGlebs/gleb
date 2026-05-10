# `gleb create`

## Purpose

Create a new `.blend` file with the Blender → Godot pipeline collection layout from `blender-godot-pipeline.md` (climbing_game repo):

- Root collections whose name starts with `_` are **never exported** (`gleb export`).
- Every other root collection is an **asset** and exports as its own `.glb`.

## Usage

```bash
gleb create <output.blend> [--asset NAME]... [--pretty] [--quiet] [--blender PATH]
```

## Arguments

| Argument       | Description                                              |
| -------------- | -------------------------------------------------------- |
| `output.blend` | Destination path. Parent directory must exist.           |

## Options

| Option           | Description                                                                 |
| ---------------- | --------------------------------------------------------------------------- |
| `--asset NAME`   | Seed one root asset `NAME` with `visual_NAME/mesh_NAME/layer_1_NAME/` and `static_NAME/trimesh_NAME/tri_layer_1_NAME/`. Repeatable. Names starting with `_` are skipped. |
| `--pretty`       | Rich terminal output instead of JSON.                                       |
| `--quiet`        | Suppress Blender stderr.                                                    |
| `--blender PATH` | Blender 5+ executable (overrides `BLENDER_PATH` / `PATH`).               |

## Why these names?

Blender **`Collection` datablock names are unique for the entire `.blend` file**, not per folder.

So one file cannot contain three collections all named `visual` or three named `layer_1`. This command embeds the **asset name** in child collection names (`visual_north_facade`, `mesh_north_facade`, `layer_1_north_facade`, …) so multi-asset levels stay readable with **no** `.001` renames from Blender.

## What Gets Created

Always:

```
(Scene Collection)
└── _support/
```

For each `--asset NAME` (NAME must not start with `_`), example `north_facade`:

```
north_facade/
├── visual_north_facade/
│   └── mesh_north_facade/
│       └── layer_1_north_facade/
└── static_north_facade/
    └── trimesh_north_facade/
        └── tri_layer_1_north_facade/
```

Add more layers in Blender: `layer_2_north_facade` under `mesh_north_facade`, `tri_layer_2_north_facade` under `trimesh_north_facade`, or add `convex_north_facade`/`cvx_layer_*`, `box_north_facade`/`box_layer_*` under `static_north_facade` — matching `gleb export` naming rules.

## Output

`summary`: `collections_created`, `assets_created`.

`data`: `assets`, `collections` (path-like entries), `output_path`.

## Examples

```bash
gleb create /tmp/level.blend
gleb create depot.blend --asset north_facade --asset south_facade --pretty
```

## Next Steps

Place meshes under `visual_<asset>/mesh_<asset>/layer_<N>_<asset>/` and collision meshes under `static_<asset>/trimesh_<asset>/tri_layer_<N>_<asset>/` (or convex/box buckets), then run `gleb export`.
