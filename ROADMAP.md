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

## v0.2 — make it move

The animation toolchain, one verb at a time, each with a real render as
evidence:

- [ ] `retopo` — Quadriflow quad remesh + triangle target (Blender backend)
- [ ] `bake` — normal/texture transfer high→low poly
- [ ] `rig` — Search-Rig / human meta-rig fitting, per-backend facing &
      up-axis conventions recorded in provenance
- [ ] `skin-check` — weight visualization + deformation render at fixed
      pose set; automatic report of suspected bad regions (eyes, fingers,
      shoulders)
- [ ] `animate` — import open mocap (CMU/LAFAN1) or hand-authored actions,
      Godot real-frame verification
- [ ] `generate` end-to-end through the framework (real pixal3d run, not
      the borrowed tarotist-repo artifact)

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
