# `gleb explore`

## Purpose

Inspect a `.blend` file and emit structured data about scene content such as objects, materials, relations, modifiers, and animation data.

## Usage

```bash
gleb explore <file.blend> [--scope SCOPE] [--object NAME]... [--match exact|contains|regex] [--ignore-case] [--pretty]
```

## Scopes

- `all` (default)
- `scene`
- `collections`
- `objects`
- `materials`
- `modifiers`
- `animations`
- `relations`

## Output Modes

- Default: compact JSON to stdout.
- `--pretty`: user-friendly terminal rendering of the same data model.
- Structure-first JSON layout: `data.structure.collections` and `data.structure.relations` come first.

## Examples

```bash
gleb explore demo.blend
gleb explore demo.blend --scope objects --object Cube
gleb explore demo.blend --scope objects --object car --match contains --ignore-case --pretty
```
