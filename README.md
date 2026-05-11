# gleb

`gleb` is a Python CLI that drives Blender in batch mode (`blender -b`) to inspect and operate on `.blend` files and 3D assets.

## Requirements

- **Python 3.12+**
- **Blender 5+** on your `PATH`, or set **`BLENDER_PATH`** to the Blender executable

## Install

From a checkout:

```bash
pip install -e .
```

Optional extras (e.g. texture helpers):

```bash
pip install -e ".[textures]"
```

This installs the `gleb` command. Confirm Blender is visible:

```bash
gleb --help
# or, if Blender is not on PATH:
BLENDER_PATH=/usr/bin/blender gleb --help
```

## Usage

```bash
# Inspect a blend file
gleb explore /path/to/file.blend --pretty

# Create a new blend file (_support/ + optional seed assets)
gleb create source/levels/depot/depot.blend --asset north_facade --asset props

# Export each root asset collection to its own .glb (ignores names starting with _)
gleb export source/levels/depot/depot.blend
gleb export source/levels/depot/depot.blend --output-dir resources/levels/depot --pretty

# Apply structured edits to a blend file
gleb edit /path/to/file.blend --op '{"type":"create_collection","name":"props"}'
```

## Docs

- `docs/DESIGN.md`
- `docs/commands/explore.md`
- `docs/commands/create.md`
- `docs/commands/export.md`

## Contributing / conda (optional)

If you prefer Conda for local development, `environment.yml` defines a reproducible env; install the package in editable mode inside that env as usual (`pip install -e .`).
