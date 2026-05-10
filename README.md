# gleb

`gleb` is a Python CLI that uses system Blender (`blender -b`) to inspect and operate on `.blend` files and 3D assets.

## Requirements

- Blender 5+ available on PATH (or set `BLENDER_PATH`)
- Miniconda installed

## Environment

```bash
conda env create -f environment.yml
conda run -n gleb pip install -e .
```

## Usage

```bash
# Inspect a blend file
conda run -n gleb gleb explore /path/to/file.blend --pretty

# Create a new blend file (_support/ + optional seed assets)
conda run -n gleb gleb create source/levels/depot/depot.blend --asset north_facade --asset props

# Export each root asset collection to its own .glb (ignores names starting with _)
conda run -n gleb gleb export source/levels/depot/depot.blend
conda run -n gleb gleb export source/levels/depot/depot.blend --output-dir resources/levels/depot --pretty

# Apply structured edits to a blend file
conda run -n gleb gleb edit /path/to/file.blend --op '{"type":"create_collection","name":"props"}'
```

## Docs

- `docs/DESIGN.md`
- `docs/commands/explore.md`
- `docs/commands/create.md`
- `docs/commands/export.md`

