# Roadmap

Public plan, honest status. Verified facts live in `docs/PROGRESS.md`;
this file is intent, not evidence.

## v0.1 — the tool layer (current)

- [x] core: task workspace + provenance ledger + backend registry
- [x] `pixal3d` backend adapter (pixal3d.cpp / trellis-cli, env-discovered)
- [x] `blender` render backend: auto-framed neutral multi-view, facing convention
- [x] stdlib GLB inspection; export refuses on structural problems
- [x] CLI + MCP frontends over the same four verbs
- [x] licensing: AGPL-3.0 + output exemption + trademark + DCO
- [ ] MCP server smoke test in CI (spawn, tools/list)

## Runtime stance

Core verbs are CPU-first: preflight, inspect, mesh (Blender CPU), bake,
export, print-check and the workflow ledger all run without a GPU. GPU
backends (MIA autorig, UniMate, future TripoSG/TripoSF/Hi3DGen trials) are
optional accelerators, discovered at runtime and reported `unavailable` with
a reason. No core verb may require a GPU to complete the local loop.

## v0.2 — make it move

The animation toolchain, one verb at a time, each with a real render as
evidence:

- [x] `retopo` / `mesh` — triangle target + watertight path verified on real
      meshes (2026-10-08); QuadriFlow still cancels on generated meshes and
      that is recorded, not hidden. `mesh --use-case` budgets ledgered
      (2026-10-16).
- [x] `bake` — normal/AO transfer high→low poly, real 958k→96k chain
      (2026-10-10)
- [x] Experimental calibrated `rig` — explicit basic-human Rigify bone data,
      automatic skinning failure and opt-in approximate weights; real chibi GLB
      animation reimport and Godot proof. No general autorig/finger claim.
- [x] Experimental external MIA v1 `autorig` — CPU inference, source preservation,
      deterministic sampling and continuity rejection; not production skinning
- [x] Experimental native `retarget` — Godot motion transfer, Blender IK and
      compulsory integer-frame hand/body checks; corrected clip only
- [ ] Further neural/manual joint fitting and validated production skinning
- [x] `skin-check` / `skin-probe` — read-only weight diagnostics and fixed-pose
      deformation probes with real tool-level evidence (2026-10-09)
- [x] Experimental `animate` (UniMate, NC-gated) — real gated clips delivered
      (2026-10-12/14); open mocap import (CMU/LAFAN1) still pending
- [x] `generate` end-to-end through the framework — real pixal3d runs recorded
      (966.56 s regeneration; golden-input chains)

## v0.3 — the moat is the spec

- [ ] provenance schema v1.0 (versioned, stable field contract)
- [ ] backend conformance suite: any third-party backend runs one pytest
      to declare compatibility
- [ ] asset catalog format: batch tasks, cache by (input sha, backend,
      params), CI-friendly
- [ ] progress streaming for long generations (MCP notifications)
- [ ] cross-platform backend discovery: CUDA builds on Windows (RTX 4070
      class: 8 GB VRAM, Q8 path expected viable at res 1024), Linux CI;
      ledger records host class because same-seed parity across machines
      is not guaranteed

## v0.4 — a face on the tool

- [ ] localhost web UI (React): task browser, render gallery, ledger
      viewer, one-click re-run. Read-only over the same engine — the UI
      is another frontend, never a second implementation.

## Explicit non-goals

- No agent framework, no custom LLM loop — orchestration belongs to the
  user's Codex/opencode/Claude.
- No hosted service. If you want that, host it yourself (AGPL applies,
  as designed).
- No cloud uploads, ever, from the core. Privacy is the product.
- No training our own 3D model; we integrate the best open ones.

## Rejected after the 2026-10-16 Tripo feature review

Formally rejected, with the evidence chain in
`docs/2026-10-16-tripo-studio-feature-review.md` §13.4. Do not re-propose
these without new evidence:

- Conversational agent panel / node-graph canvas (Astra, forge3d). The user's
  own agent plus the `figura_*` tool surface is the interface; UI is not a
  goal. `review`-style approval semantics already exist as `visual_approval`.
- Cloud refinement products (Pro Refine-style), cloud motion libraries,
  video-to-motion services — any pipeline that uploads the user's art.
- Credits / paywall / quota mechanics and A/B or telemetry infrastructure
  (session replay, marketing pixels) — contrary to the privacy promise.
- The 9-DCC plugin/bridge matrix — files + one Blender-verified path instead.
- Multi-view image input generation — single-view contract stands
  (docs/2026-10-07-tripo-parity-analysis.md §2.1).
- Text-to-3D on cloud models; revisit only if a local text-conditioned
  backend is integrated.
- 8K textures as a scheduled goal; first prove 4K is meaningful
  (parity doc §2.3).

## Rejected after the 2026-10-16 Meshy/Hi3D review

Evidence: `docs/2026-10-16-meshy-hi3d-feature-review.md`. Same rule: no
re-proposal without new evidence.

- AI video generation (Meshy's text/image-to-video via fal.ai et al.) — not a
  3D asset toolchain capability and cloud-only.
- Physical-product commerce and print-on-demand (Meshy Creative Lab, Hi3D
  Maker Workshop ordering), contest/community gamification, desktop chat
  clients, cloud agent sessions — service/business surfaces, not tooling.
- DCC *and slicer* plugin matrices (Bambu Studio, OrcaSlicer, Cura,
  Creality, Elegoo, Lychee, Unity/Unreal/Roblox/3ds Max/Blender) — files
  plus one Blender-verified path.
- Sparc3D code/weights (Math Magic gate: "code may be released upon
  approval"); do not obtain or vendor them.

## Proposed after the Meshy/Hi3D review (needs human sign-off)

- [x] `print-check` — local printability report: open/non-manifold edges,
      zero-area/duplicate faces, connected shells, overhang area beyond a
      configurable angle, bed-contact area, build-volume fit, and an optional
      pymeshlab shape-diameter wall proxy (CPU, external runtime). Report
      only, no auto-repair claim. Self-intersections stay open.
      Evidence: `.local/runs/2026-10-16-print-check/` and PROGRESS.
- [ ] `--dry-run` / plan preview for long workflows: print the planned steps
      and rough budgets before executing (Meshy CLI's `make --dry-run`
      pattern, without credits).
- [ ] Split/color preview: split a GLB into parts by material/vertex-color
      clustering and emit per-part files + assembly notes; connectors
      (mortise/ball joints) stay out of scope until split is proven.
- [ ] CUDA trials on the Windows RTX box: TripoSG (generation), Hi3DGen
      (normal-bridging geometry) and TripoSF (watertight reconstruction).
      Runbook: `docs/2026-10-17-gpu-trial-runbook.md`; all three are optional
      accelerators and never required for the CPU-first core loop.

## Independent integrations after 3DGenStudio review

- [ ] Persistent external jobs and per-GPU resource scheduling (CPU workers separate)
- [ ] ComfyUI adapter with versioned workflows and explicit local endpoints
- [x] UV (smart project + quality metrics), triangle-decimate retopo and
      high/low normal/AO baking — done as `mesh uv` / `mesh retopo` / `bake`;
      editable quad retopology stays unsolved and honestly recorded
- [ ] Skin/animation transfer preserving existing GLB buffers and materials
- [ ] SkinTokens and MoCapAnything trials on suitable NVIDIA GPU; no GPU result yet
- [ ] Single-view albedo/PBR refinement evolution (multi-view input is rejected above)

Priorities and source/permission boundaries: `docs/2026-10-08-3dgenstudio-review.md`.
