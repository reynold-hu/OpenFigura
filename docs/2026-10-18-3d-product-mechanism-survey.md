# 3D product mechanism survey — 2026-10-18

Public-source survey of how current AI 3D products expose their generation
pipeline. Scope is **public documentation, publicly shipped client code on
this machine, and public API schemas bundled with it**. No vendor service was
called, no non-public implementation was copied, and nothing here is a parity
claim. Claims are split into **observed / inferred / unknown**.

## Sources

- Local ComfyUI desktop **0.22.2** (`%LOCALAPPDATA%\Programs\ComfyUI`,
  `resources/ComfyUI/comfyui_version.py` = `0.22.2`), including its bundled
  public API-node schemas for Meshy, Tripo, Hunyuan3D and Rodin.
- Public product pages searched 2026-10-18: tripo3d.ai / developers.tripo3d.com,
  hi3d.ai, and the ComfyUI node inventory. Public marketing claims are marked
  as such.
- REA static analysis of the ComfyUI Electron shell (`app.asar`, REA 6.7.0)
  was started but is **partial**: the archive contains 11,702 JavaScript
  artifacts and the run was still processing bundled `node_modules` at survey
  time (progress log retained under `.local/runs/2026-10-18-newstack/`).
  Mechanism findings below come from the public Python API-node schemas, not
  from the partial shell graph; the shell graph is supplementary.

## What the products expose (observed)

### Meshy (public API schema in `comfy_api_nodes/apis/meshy.py`)
- Task families: text→model (preview → **refine**), image→model, multi-image→
  model, **rig**, **animate**, **texture**, remesh.
- Generation controls: `ai_model`, `topology` = quad | triangle,
  `target_polycount` 100–300000 (default 300000), `should_remesh`,
  `symmetry_mode` = auto | on | off, `pose_mode`, `seed`, `moderation`.
- Rigging takes `height_meters`; animation takes `rig_task_id` + `action_id`.
- Texture task re-textures an existing task with optional original UV, PBR,
  text/image style prompt.
- Outputs: GLB / FBX / USDZ / OBJ URLs plus PBR maps
  (base_color, metallic, normal, roughness).

### Tripo (public API schema in `comfy_api_nodes/apis/tripo.py`)
- Model versions v1.4 (2024-06-25) through **v3.1 (2026-02-11)**.
- Task chain: text/image/multiview→model, texture, refine,
  **animate_prerigcheck → animate_rig → animate_retarget**, stylize, convert.
- Topology `bip` | `quad`; skeleton spec `mixamo` | `tripo`; face limit
  −1..2,000,000; texture/geometry quality standard | detailed; PBR.
- Animation presets: idle, walk, run, dive, climb, jump, slash, shoot, hurt,
  fall, turn, plus quadruped/hexapod/octopod walk.
- **FBX presets: blender | mixamo | 3dsmax**; convert targets GLTF / USDZ /
  FBX / OBJ / STL / **3MF**.

### Hunyuan3D (Tencent; public schema in `comfy_api_nodes/apis/hunyuan3d.py`)
- Models **3.0 / 3.1** (LowPoly option unavailable on 3.1).
- Tasks: text→model, image(s)→model with back/left/right views, To3D Pro,
  **Model to UV**, **3D Part** (part decomposition), **3D Texture Edit**,
  **Smart Topology** (polygon type + face level).
- Face count 3,000–1,500,000 (default 500,000); PBR optional; generate type
  Normal / LowPoly / Geometry.

### Hi3D (public pages, marketing claims)
- Text / image / sketch / multi-view → 3D.
- Automatic **printable part splitting**, relief generation, editing workspace.
- V3.0 announced as "2048³ voxel" geometry (vendor claim, not measured here).

### ComfyUI local 3D surface (observed in 0.22.2)
- Nodes: `Load 3D & Animation` (gltf/glb/obj/fbx/stl/spz/splat/ply/ksplat),
  `Preview 3D & Animation`, `Save 3D Model` (GLB), Stable3D conditioning
  (Zero123 / SV3D) for novel views.
- Integrated remote 3D providers: Meshy, Tripo, Hunyuan3D, Rodin.

## Inferred mechanism pattern (inference, not observed internals)

All four converge on the same pipeline shape, visible from their public task
contracts: **generate coarse/draft → refine → remesh/topology choice → texture
(PBR) → optional rig → optional animate/retarget → format export**, with a
task-id/polling lifecycle and explicit polycount/topology/symmetry controls.
The "quality" tiers map to model versions plus geometry/texture quality
enums rather than hidden switches. Part decomposition (Hunyuan3D "3D Part",
Hi3D print splitting) is a separate post-generation task.

## Unknowns

- Actual network architectures, training data, and sampler internals: not
  public, not inspected, not needed for our design decisions.
- Real wall-clock/quality of vendor models on this hardware: not measured.
- Hi3D's 2048³ voxel claim and part-split robustness: vendor marketing,
  unverified here.

## Implications for OpenFigura (design choices, not parity)

Already present after the 2026-10-17/18 update: symmetry preflight, use-case
polycount budgets (`presets`), FBX/OBJ/STL/USD export, preflight face check.
Worth adopting from the observed contracts, in our own implementation:

1. **Explicit topology choice per export** (quad vs triangle/bip) with the
   resolved value ledgered — we already ledger retopo targets; add a topology
   field to the export record.
2. **Symmetry mode as a generation/preflight control** (auto/on/off) — we
   have silhouette symmetry preflight; surface it as an explicit parameter
   when a backend supports it.
3. **Rig → animate as a gated chain with a pre-rig check** (Tripo does a
   separate `animate_prerigcheck`): matches our preflight → autorig →
   animate → contact-gate chain; keep the pre-rig check explicit.
4. **Engine FBX presets** (blender/mixamo/3dsmax) — our new export presets
   should state which target they serve and record it.
5. **Task-id lifecycle with explicit status/progress** — our ledger already
   records steps/exit codes; no change needed.
6. **Part decomposition and UV/smart-topology as separate verbs** — Hunyuan3D
   exposes them separately; we should not hide them inside generation.

## Positioning note

This survey studies public interfaces to decide what to build. No vendor code
is vendored, no non-public implementation is used, and no parity is claimed.
