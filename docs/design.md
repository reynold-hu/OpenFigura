# OpenFigura design

## Layering (the one rule that matters)

```
LLM / agent (yours: Codex, opencode, Claude, pi)   ← intent, planning, retries
        │ MCP tools or CLI (identical verbs)
        ▼
openfigura-core                                     ← deterministic pipeline glue
  task workspace · provenance ledger · backend registry · GLB inspection
        │
        ▼
backends                                            ← real capability
  pixal3d.cpp (generate) · Blender (render, retopo, rig) · yours tomorrow
```

The LLM never touches geometry. Backends never improvise. Core never lies:
a step records what actually ran (command, exit code, wall time, hashes)
or the run is marked failed.

## The four verbs (v0.1) → six (v0.2)

| verb | contract | failure mode |
|---|---|---|
| generate | staged image + params → `artifacts/model.glb` | backend unavailable → RuntimeError with probe reason |
| render | GLB → auto-framed neutral multi-view PNGs | no Blender → probe says so; frames=[] → status fail |
| inspect | GLB → structural JSON (stdlib parser, no deps) | problems[] → export refuses |
| export | verified artifacts + ledger → delivery folder | refuses on inspection problems |
| retopo/rig/skin-check/animate (v0.2) | same task workspace, same ledger | same rules |

CLI and MCP are *thin mirrors* of `core/engine.py`. Adding a verb means
adding it to the engine first; frontends never gain private behavior.

## Task workspace & provenance

One directory per asset run, relocatable, everything relative:

```
<task-id>/
  input/            reference image + sha256
  artifacts/        model.glb (+ v0.2 outputs)
  render/           neutral frames
  inspect.json      structural report
  provenance.json   append-only ledger: step, utc, command, exit, wall,
                    hashes, backend, params
```

`provenance.json` is the unit of trust. An asset without a ledger that
re-runs is not an asset, it's a screenshot. Schema is versioned with the
package; v1.0 freeze is a v0.3 deliverable (ROADMAP).

## Backend protocol

```python
class Backend(Protocol):
    id: str; kind: str                      # "generate"|"render"|"postprocess"
    def capabilities() -> Capabilities      # available, hardware, reason, notes
    # plus verb methods (generate/render_views/…) returning ledger dicts
```

Design rules, learned the expensive way (2026-10-05 trials):

- **Discovery via env, never paths baked in**: `OPENFIGURA_PIXAL_RUNTIME`,
  `OPENFIGURA_PIXAL_MODELS`. Missing binary is a *reported state*, not a
  crash.
- **Backend-declared preprocessing is a pipeline stage, not a hidden
  side effect.** If a backend exposes `prepare_input`, the engine runs it
  before generation and records a separate `preprocess` ledger entry
  (command, exit, hashes). Pixal3D uses it for the SV flow's mandatory
  alpha matte (`--bg-only`, BiRefNet when present); the OS-specific part
  (Metal/CUDA build, device choice) stays inside the runtime, so the
  adapter remains OS-agnostic and only reports `platform` in capabilities.
- **Generators have conventions; record them.** Pixal3D output faces +Y
  (our default front camera saw its back). `facing_deg` is an explicit
  render parameter and lands in the ledger. New backends must declare
  facing/up-axis in `capabilities().notes`.
- **Long runs are normal**: 27 min for one 1024-res generation on M5/16GB.
  Tool timeouts must be generous; progress streaming is v0.3.
- **Weights are fetched, never shipped.** License of each component travels
  in the ledger, not in our repo.

## Rendering is the quality gate

Judgment happens on neutral auto-framed multi-view renders (orthographic,
three area lights scaled to the model's bounding box), never on the
generator's own preview. Inspection is structural (attributes, PBR refs,
triangle counts); aesthetic approval is a separate, human verdict — the
ledger has a `visual_approval` field that only humans set.

## Non-goals

Agent loop, hosted service, cloud upload, training our own model,
competitive claims without same-input comparisons.

## Experimental refinement and calibrated binding

`engine.refine_texture` preserves a static source and emits `model-refined.glb`;
`engine.rig` preserves its source and emits `model-rigged.glb/.blend` using explicit
calibration. CLI and MCP mirror both operations. Renderer `frame` selection uses
frame-1 camera bounds and ignores hidden bone display meshes. Inspection reports
skins, deform joint counts and animation names; those fields are structural, not
deformation acceptance. Rigify basic-human binding has no finger chains. Capsule
weights are explicitly selected and remain an approximation, never a fallback
reported as successful Bone Heat. See calibrated-rigging.md for contracts.
