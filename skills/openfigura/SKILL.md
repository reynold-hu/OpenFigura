---
name: openfigura
description: Local, auditable 3D asset production with OpenFigura. Use when the user wants to turn a reference image into a textured GLB, rig or animate a character, run mesh post-processing, check printability, or produce a provenance-ledgered export without uploading art to a cloud service.
---

# OpenFigura

OpenFigura is an independent open-source (AGPL-3.0) local 3D asset toolchain.
It runs on the user's machine, never uploads reference art, and records every
step in `provenance.json`. **CPU-first**: the core verbs work without a GPU;
GPU backends (MIA autorig, UniMate motion, future model trials) are optional
accelerators and report `unavailable` with a reason when missing.

## Setup

- Repo install: `python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`.
- MCP (preferred): register `openfigura-mcp` as a local stdio server.
- Verify first: `openfigura backends` and `openfigura syscheck`. Read the
  output; never assume a backend exists.

## One workflow

1. `openfigura preflight ref.png` — errors stop; warnings are decisions.
   Add `--face` for realistic portraits: it estimates the face size at 1024
   and warns about cropping (stylized art may report `no_face`; not an error).
2. `openfigura new ref.png -o tasks/ --name asset`
3. `openfigura generate tasks/asset --backend pixal3d --seed 42` — long run;
   use a generous timeout and never fake completion. Unsure? Add `--dry-run`
   first: it prints preflight, steps and params and writes nothing.
4. `openfigura inspect tasks/asset` — `ok:false` means do not export.
5. Optional: `openfigura print-check tasks/asset --params '{"build_volume_mm":[256,256,256]}'`
   Optional readiness check: `openfigura score tasks/asset` (never an
   aesthetic verdict; human review stays pending).
6. `openfigura render tasks/asset --samples 32` — Pixal3D output faces +Y,
   so add `--facing 180` for the front view.
7. `openfigura export tasks/asset --dest dist/` — engine-bound FBX:
   `--format fbx --fbx-preset blender|godot|unity|unreal`.
8. Final handoff: `openfigura evaluate tasks/asset` writes JSON + a markdown
   report for the human (optional glTF-Validator/trimesh when configured).

Every step appends to the ledger. To audit or reproduce an asset, read
`provenance.json`, not chat history.

## Rules

- `visual_approval` is a human field. Show renders; never declare "good".
- One reference view per generate; never feed a multi-view sheet to a
  single-view backend.
- Reuse the recorded seed for "the same" asset; a new seed is a new candidate.
- Failures are data: keep the task folder; never edit history.
- Mesh budgets: `mesh --use-case game|animation|print|vr_ar|product_display|general`
  fills retopo faces / optimize ratio only when params do not set them;
  explicit params always win.
- `print-check` is report-only. Wall thickness is an optional CPU proxy only
  when `OPENFIGURA_PYMESHLAB_PYTHON` points at a Python with pymeshlab;
  otherwise the section says `unavailable`.

## Tool map (CLI ↔ MCP mirrors)

`new`/`figura_new_task` · `preflight`/`figura_preflight` ·
`generate`/`figura_generate` · `inspect`/`figura_inspect` ·
`render`/`figura_render` · `print-check`/`figura_print_check` ·
`export`/`figura_export` · `score`/`figura_score` · `evaluate`/`figura_evaluate` · `mesh`/`figura_mesh` · `presets`/`figura_presets` ·
`workflow-*`/`figura_workflow_*` · `execute`/`figura_execute` ·
`autorig`/`figura_autorig` · `retarget`/`figura_retarget` ·
`animate`/`figura_animate` · `skin-check`/`figura_skin_check` ·
`skin-probe`/`figura_skin_probe` · `pivot`/`figura_pivot` ·
`bake`/`figura_bake` · `refine-texture`/`figura_refine_texture`.
