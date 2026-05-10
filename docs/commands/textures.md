# `gleb textures`

Host-side helpers for Godot-oriented texture preparation: pack ORM maps, handle Megascans-style decal folders, generate `orig` / `half` / `quarter` / `eighth` folders, and write `.import` stubs next to ORM images. **Blender is not used.**

## Dependencies

Install optional extras:

```bash
pip install 'gleb[textures]'
```

This pulls in **numpy** and **Pillow**. Optional EXR reading (Polyhaven) still benefits from **opencv-python** or **imageio** in the same environment.

---

## `gleb textures process`

Runs the full pipeline on a **directory**:

- If the path contains **only subdirectories** (and is not already a pre-tiered layout), each **child directory** is treated as one texture **set**.
- If the path is a **single set** (images or pre-built `orig`/`half`/`quarter`), that folder is processed alone.

### Detection

| Layout | Behavior |
| ------ | ---------- |
| `orig/`, `half/`, `quarter/` present | Optionally create `eighth/` from `orig/`; run convention-based ORM in each tier; write stubs. |
| Megascans decal (`BaseColor` + `Opacity` in `.jpg` names) | Build Albedo + ORM, downscale, stubs. |
| FAB (`*_ao`, `*_roughness`, `*_metalness` suffixes) or Polyhaven (`*_ao_*`, `*_rough_*`, …) | Build ORM, downscale, stubs. |
| Neither | Set is reported as skipped (`skip: unknown set`). |

### Downscaling

Only **`.jpg` / `.png`** files in the **set root** are moved into `orig/` and duplicated at half, quarter, and eighth resolutions. **EXR** files are not moved by this step (convert or rely on ORM output as PNG).

### Usage

```
gleb textures process <dir> [--json | -j] [--pretty | -p] [--quiet | -q]
```

### Terminal vs scripts

| Situation | Stdout | Stderr |
| --------- | ------ | ------ |
| Interactive terminal (TTY) | **Rich** summary + full pipeline log panel | Short **phase lines** (`[gleb textures] …`) during work |
| Pipe / redirect / CI (`stdout` not a TTY) | **JSON** envelope (one line) | No phase lines unless stderr is a TTY |

Override:

- **`--json` / `-j`** — always print JSON (agents, `jq`, logs).
- **`--pretty` / `-p`** — always print Rich (even when piping).
- **`--quiet` / `-q`** — suppress phase lines on stderr; JSON unchanged.

### JSON envelope

| Field | Meaning |
| ----- | ------- |
| `meta.runtime` | `"host"` |
| `meta.command` | `"textures.process"` |
| `meta.path` | Resolved input directory |
| `summary.sets_total` | Number of set records returned |
| `summary.sets_skipped` | Count of sets whose `outcome` starts with `skip:` |
| `data.sets` | `[{ "name", "outcome" }, ...]` |
| `data.messages` | Ordered pipeline log lines (same content agents need to explain skips) |
| `warnings` | Non-fatal issues (e.g. failed image read) |
| `errors` | Fatal issues (empty on success) |

---

## `gleb textures orm`

Pack **explicit** grayscale inputs into one **8-bit RGB PNG** with Godot ORM channel order:

- **R** — ambient occlusion  
- **G** — roughness  
- **B** — metallic  

Missing channels use the same defaults as convention-based ORM: AO=white (255), roughness=medium grey (128), metallic=black (0). At least **one** of `--ao`, `--roughness`, or `--metallic` is required.

### Usage

```
gleb textures orm --output <path.png> [--ao PATH] [--roughness PATH] [--metallic PATH]
                  [--json | -j] [--pretty | -p]
```

Same **TTY vs pipe** rules as `textures process`: interactive terminals show Rich by default; use **`--json`** for machine-readable stdout.

### JSON envelope

| Field | Meaning |
| ----- | ------- |
| `meta.runtime` | `"host"` |
| `meta.command` | `"textures.orm"` |
| `meta.output` | Target path from `--output` |
| `meta.ao` / `meta.roughness` / `meta.metallic` | Resolved paths or `null` |
| `summary.width` / `summary.height` | Output dimensions (max of provided maps, or 1024 if none valid) |
| `data.output_path` | Absolute path written |
| `data.messages` | Build log lines |

Exit code **2** if no channel flags are provided.

---

## Agent notes

- Use **`--json` / `-j`** so stdout is always the JSON envelope (do not rely on TTY detection in automation).
- **`data.messages`** duplicates the human-readable pipeline narrative for debugging without parsed stderr.
- Filename conventions for `process` are strict; use `textures orm` when maps do not follow FAB/Polyhaven naming.
