# Design Document

## Goals

- Provide a natural-feeling CLI over Blender background mode operations.
- Keep command behavior deterministic and machine-friendly by default — primary consumer is AI agents.
- Expose a consistent JSON envelope across every command so agents can handle success and failure uniformly.
- Share logic across commands through reusable command utility modules.

---

## Architecture

`gleb` is split between two execution environments:


| Layer         | Location                               | Runs in                |
| ------------- | -------------------------------------- | ---------------------- |
| CLI / runtime | `gleb/*` (excluding `blender_scripts`) | host conda env         |
| Probe scripts | `gleb/blender_scripts/*`               | Blender Python (`bpy`) |


Data flow for every command:

```
CLI args
  → normalize & validate (command_utils.py)
  → build JSON payload
  → base64-encode payload
  → blender -b [<file.blend>] --python <probe.py> -- <encoded_payload>
  → extract last JSON line from stdout
  → validate with Pydantic model
  → emit (JSON by default, Rich if --pretty)
```

Commands that operate on an existing file pass it after `-b`. Commands that create a new file
(e.g. `create`) omit it; Blender opens an empty default scene.

Each command follows the same file layout:

```
gleb/commands/<cmd>.py               # CLI definition (Typer)
gleb/commands/<cmd>_utils.py         # payload building, schema wiring
gleb/blender_scripts/<cmd>_probe.py  # bpy logic, always prints one JSON line
gleb/models/<cmd>_schema.py          # Pydantic input/output models
gleb/formatters/<cmd>_pretty.py      # optional Rich renderer
```

---

## Output Contract

All commands emit a single JSON object to stdout. The envelope shape is identical regardless of command:

```json
{
  "meta":     { "file": "...", "blender_version": "5.x", "command": "..." },
  "summary":  { ... },
  "data":     { ... },
  "warnings": [],
  "errors":   []
}
```

- `meta` — provenance: source file, Blender version, command name, and any echoed options.
- `summary` — small counts object; agents can assess results without parsing `data`.
- `data` — full structured payload; shape is command-specific and documented per command.
- `warnings` — non-fatal issues (e.g. skipped objects, missing optional data).
- `errors` — fatal issues; populated when a graceful partial result is still emitted.

On a fatal error the same envelope is printed and the process exits non-zero. Agents should always parse JSON first and only fall back to stderr for raw diagnostic context.

### Exit Codes


| Code | Meaning                                  |
| ---- | ---------------------------------------- |
| `0`  | Success                                  |
| `1`  | Operation error (details in `errors[]`)  |
| `2`  | Bad arguments / usage error              |
| `3`  | Blender not found or unsupported version |


### Output Modes

- Default: compact JSON to stdout, intended for agents and pipes.
- `--pretty`: Rich-rendered terminal view of the same validated model — no JSON emitted.
- `--quiet`: suppress Blender stderr noise; only the final JSON envelope goes to stdout.

### Common Flags (all commands)


| Flag               | Description                                                                 |
| ------------------ | --------------------------------------------------------------------------- |
| `--blender <path>` | Override Blender executable (falls back to `BLENDER_PATH` env, then `PATH`) |
| `--pretty`         | Human-readable Rich output                                                  |
| `--quiet`          | Suppress non-JSON output                                                    |


The `edit` command additionally accepts:


| Flag              | Description                                                               |
| ----------------- | ------------------------------------------------------------------------- |
| `--output <path>` | Write result to a new file; leave source untouched                        |
| `--dry-run`       | Validate and plan the operation, emit what *would* change, make no writes |


---

## Version Policy

- Blender major version `5+` is required.
- Version is checked before every probe execution.
- Version string is always echoed in `meta.blender_version`.

---

## Commands

### `gleb explore`

Read-only inspection of a `.blend` file. See `docs/commands/explore.md` for full reference.

```
gleb explore <file.blend> [--scope SCOPE] [--object NAME]... [--match exact|contains|regex]
             [--ignore-case] [--detail] [--diagnose] [--pretty] [--quiet] [--blender PATH]
```

Scopes: `all`, `scene`, `collections`, `objects`, `materials`, `modifiers`, `animations`,
`relations`, `constraints`, `geometry`, `textures`, `armatures`, `libraries`, `custom_properties`.

---

### `gleb create`

Create a new `.blend` file bootstrapped with the flat Blender → Godot pipeline layout (`_support/` plus optional seed asset collections).
See `docs/commands/create.md` for full reference.

```
gleb create <output.blend> [--asset NAME]... [--pretty] [--quiet] [--blender PATH]
```


| Option           | Description                                                                          |
| ---------------- | ------------------------------------------------------------------------------------ |
| `--asset NAME`   | Seed one root asset with `visual_NAME/mesh_NAME/layer_1_NAME/` and `static_NAME/trimesh_NAME/tri_layer_1_NAME/`. Repeatable. |


`summary` fields: `collections_created`, `assets_created`.

`data` fields: `assets` (list), `collections` (list, may include path-like names), `output_path`.

---

### `gleb export`

Export each non-`_` root collection from a `.blend` as its own `.glb` for Godot import.
Stamps `godot_type` / `render_layers` or `collision_layer` / `collision_mask` from
per-asset folders such as `visual_<asset>/mesh_<asset>/layer_<N>_<asset>/` and
`static_<asset>/trimesh_<asset>/tri_layer_<N>_<asset>/` (and `convex_*`/`cvx_layer_*`, `box_*`/`box_layer_*`).
Collection datablock names are global in Blender.
See `docs/commands/export.md` for full reference.

```
gleb export <file.blend> [--output-dir DIR] [--asset NAME]...
            [--no-apply-modifiers] [--no-export-tangents] [--materials EXPORT|PLACEHOLDER|VIEWPORT|NONE]
            [--pretty] [--quiet] [--blender PATH]
```


| Option                   | Description                                                                        |
| ------------------------ | ---------------------------------------------------------------------------------- |
| `--output-dir DIR`       | Directory for `.glb` output. Defaults to `<blend_dir>/export/`.                    |
| `--asset NAME`           | Export only this root asset (repeatable). Exports all non-`_` roots when omitted.  |
| `--no-apply-modifiers`   | Disable glTF “Apply Modifiers” (default applies; needed for shape keys).           |
| `--no-export-tangents`   | Omit vertex tangents from glTF (default exports tangents for normal maps).        |
| `--materials MODE`       | Blender glTF material export mode (`EXPORT`, `PLACEHOLDER`, `VIEWPORT`, `NONE`).   |


`summary` fields: `assets_exported`, `assets_skipped`, `assets_failed`.

`data` fields: `output_dir`, `exports` (list of `{asset, path, status}`).

---

### `gleb edit`

Apply structured modifications to a `.blend` file. Operations are expressed as JSON objects and
applied in order. This is the primary agent-facing mutation surface.

```
gleb edit <file.blend>
          (--op JSON | --ops-file PATH)...
          [--output PATH] [--dry-run] [--pretty] [--quiet] [--blender PATH]
```


| Option              | Description                                              |
| ------------------- | -------------------------------------------------------- |
| `--op <json>`       | A single operation object (repeatable)                   |
| `--ops-file <path>` | JSON file containing an array of operation objects       |
| `--output <path>`   | Write modified file to this path; leave source unchanged |
| `--dry-run`         | Plan operations, emit what would change, write nothing   |


Operations from `--op` flags and `--ops-file` files are concatenated into a single list in the
order they appear on the command line.

#### Operation Catalog

Every operation is a JSON object with a required `"type"` field.

---

**Objects — identity**

```json
{ "type": "rename_object", "from": "Cube", "to": "Body" }
```

Rename an object datablock. Fails if `from` does not exist or `to` is already taken.

---

**Objects — topology**

```json
{ "type": "join_objects", "objects": ["Body", "Door_L", "Door_R"], "into": "CarBody" }
```

Join two or more mesh objects into one. `objects[0]` is the surviving base; the rest are merged
into it. The result is renamed to `into`. All objects in the list must be of the same type (MESH).
Fails if any named object does not exist.

`into` is optional; when omitted the name of `objects[0]` is kept.

```json
{ "type": "delete_object", "object": "Lamp" }
```

```json
{ "type": "duplicate_object", "object": "Cube", "to": "CubeCopy" }
```

`to` is optional; when omitted Blender's default naming is used.

**Objects — create**

```json
{ "type": "create_object", "name": "NewMesh", "object_type": "MESH", "collection": "MyCollection" }
```

Create a new object. `object_type` is `MESH` (empty mesh) or `EMPTY`. `collection` is optional; when
omitted the object is linked to the scene’s root `Scene Collection`. Fails if `name` is already
used or the target collection does not exist.

---

**Collections**

```json
{ "type": "create_collection", "name": "Props", "parent": "Scene Collection" }
```

Create a new collection. `parent` is optional; when omitted the collection is linked as a child of
the master scene collection. Fails if the name already exists or `parent` is not found.

```json
{ "type": "rename_collection", "from": "Collection", "to": "Env" }
```

```json
{ "type": "link_object_to_collection", "object": "Cube", "collection": "Props" }
```

```json
{ "type": "unlink_object_from_collection", "object": "Cube", "collection": "Collection" }
```

Unlink fails if the object would belong to no collection afterward — link it elsewhere first (e.g.
`move_object_to_collection` links before unlinking).

```json
{ "type": "move_object_to_collection", "object": "Cube", "from_collection": "Collection", "to_collection": "Props" }
```

Links the object into `to_collection`, then unlinks from `from_collection`. Safe ordering so the
object always stays in at least one collection.

---

**Modifiers**

```json
{ "type": "add_modifier", "object": "Body", "modifier_type": "SUBSURF", "name": "Subdivision",
  "settings": { "levels": 2, "render_levels": 3 } }
```

Add a modifier of `modifier_type` to an object. `name` is optional (defaults to Blender's name for
that type). `settings` is an optional dict of modifier property names mapped to values — only the
provided keys are set; all others keep their defaults.

Common `modifier_type` values: `SUBSURF`, `SOLIDIFY`, `ARRAY`, `BEVEL`, `BOOLEAN`, `MIRROR`,
`DECIMATE`, `SMOOTH`, `WEIGHTED_NORMAL`, `DISPLACEMENT`, `ARMATURE`, `CURVE`, `SHRINKWRAP`.

```json
{ "type": "apply_modifiers", "object": "Body", "names": ["Subdivision"] }
```

Collapse (apply) modifiers permanently. `names` is optional; when omitted all modifiers are applied
in stack order.

```json
{ "type": "remove_modifier", "object": "Body", "name": "Subdivision" }
```

Remove a modifier by name without applying it.

---

**Materials — datablocks**

```json
{ "type": "rename_material", "from": "Material", "to": "BodyPaint" }
```

Rename a material datablock. All objects referencing it see the new name automatically.

---

**Materials — slots**

Material slots are per-object. An object can have zero or more slots; each slot either holds a
material reference or is empty.

```json
{ "type": "set_material", "object": "Body", "slot": 0, "material": "BodyPaint" }
```

Assign an existing material to a slot by index. Fails if the slot does not exist or the material
datablock is not found.

```json
{ "type": "add_material_slot", "object": "Body", "material": "Chrome" }
```

Append a new slot. `material` is optional; when omitted the slot is created empty.

```json
{ "type": "remove_material_slot", "object": "Body", "slot": 1 }
```

Remove a slot by index. Slots above the removed index shift down.

```json
{ "type": "clear_material_slots", "object": "Body" }
```

Remove all material slots from the object.

---

**Properties**

```json
{ "type": "set_custom_property", "object": "Body", "key": "lod_level", "value": 1 }
```

Set an object-level custom property (`obj[key] = value`). `value` must be JSON-serialisable.

```json
{ "type": "set_scene_property", "path": "render.resolution_x", "value": 1920 }
```

Set a scene-level property via dotted path relative to `bpy.context.scene`.

---

#### Edit Output

`summary` fields: `operations_total`, `operations_applied`, `operations_skipped`, `operations_failed`.

`data.operation_results` — one entry per operation in input order:

```json
{
  "index":  0,
  "type":   "rename_object",
  "status": "applied",
  "detail": "Renamed 'Cube' → 'Body'"
}
```

`status` values:


| Value         | Meaning                                                         |
| ------------- | --------------------------------------------------------------- |
| `applied`     | Operation succeeded and was written                             |
| `skipped`     | Operation was a no-op (e.g. object already had the target name) |
| `failed`      | Operation could not be completed; reason in `detail`            |
| `would_apply` | Dry-run: operation would succeed                                |
| `would_skip`  | Dry-run: operation would be a no-op                             |


If any operation has `status: failed`, exit code is `1` and the failure details also appear in the
top-level `errors[]` array. Preceding operations that already succeeded are not rolled back.

---

### `gleb textures`

Host-side Godot texture workflow (ORM packing, decals, mip folders, `.import` stubs). Does **not**
run Blender. See [`docs/commands/textures.md`](commands/textures.md).

```
gleb textures process <dir> [--pretty] [--quiet]
gleb textures orm --output <path.png> [--ao PATH] [--roughness PATH] [--metallic PATH] [--pretty]
```

Requires optional dependencies: **`pip install 'gleb[textures]'`** (numpy, Pillow).

---

## Host-side commands

Commands under **`gleb textures`** execute in the **same Python environment as the CLI** (not in
Blender). They emit the same JSON envelope shape as probe-backed commands.

| Field | Host-side behavior |
| ----- | ------------------ |
| `meta.runtime` | `"host"` |
| `meta.command` | e.g. `"textures.process"`, `"textures.orm"` |
| `meta.blender_version` | **Omitted** — Blender is not invoked |
| `--blender` | Not applicable |

For **`gleb textures`**, stdout defaults to **Rich** when connected to an interactive terminal and **JSON**
otherwise (pipes, redirects). Use **`--json`** to force the envelope for agents and scripts; **`--pretty`**
forces Rich output. Phase lines may print to **stderr** during long runs (`--quiet` suppresses them).

---

## Extensibility

To add a new command, follow this checklist:

1. `gleb/commands/<cmd>.py` — Typer command function, error envelope, `--pretty` branch.
2. `gleb/commands/<cmd>_utils.py` — payload construction, schema wiring, call to `run_blender_probe` (or `run_blender_script` for commands that create new files).
3. `gleb/blender_scripts/<cmd>_probe.py` — `bpy` logic; always `print(json.dumps(result))` exactly once as the last line.
4. `gleb/models/<cmd>_schema.py` — Pydantic models for result; always include `meta`, `summary`, `data`, `warnings`, `errors`.
5. Pretty renderer — either a dedicated `gleb/formatters/<cmd>_pretty.py` (Rich module) or an inline `_render_<cmd>_pretty()` function in the command file. Either pattern is acceptable.
6. Register with `app.command("<cmd>")` or `app.add_typer(...)` in `gleb/cli.py`.
7. Add `docs/commands/<cmd>.md` with purpose, usage, options, and output field reference.

**Host-only commands** (no Blender): put shared logic under `gleb/texture_pipeline/` or a similar
package; skip steps 3 and the probe runner; set `meta.runtime` to `"host"` in the schema.

