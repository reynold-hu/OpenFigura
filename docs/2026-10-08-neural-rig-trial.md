# External rigging and motion trial — 2026-10-07 to 2026-10-08

Evidence root: `~/Desktop/openfigura-neural-rig-trial-2026-10-07/`.
The work began on October 7; final integration/3DGenStudio review continued on
October 8. These are real local results, not paper benchmark numbers.

## Installed and used

Make-It-Animatable **v1**, source `8fb51382ff6da556cdb95cc03a48200603f3a493`.
External Python3.11.15 CPU environment under its source checkout. Reviewed source
and checkpoint metadata are pinned in `mia-runtime-manifest.json`. No hosted mesh
upload, no manual bone coordinates, no capsule fallback and no authored FK angles.

Torch2.1.2 CPU / bpy4.3.0 / torch-cluster1.6.3 CPU / PyTorch3D0.7.7 **pure transforms**.
The whole PyTorch3D compiled mesh-operator suite is not installed or claimed.
CPU build problems and their actual logs: old Torch pkg_resources dependency
(setuptools<81) and Clang invalid-specialization diagnostic (compiler flags), plus
missing shapely at hand-region slicing. Initial failed trials are retained.

Three checkpoints (1.37GB total) were size/SHA-verified; initial interrupted downloads
were rejected, then range-resumed and verified. `verified-checkpoints.json` records
exact hashes. The Mixamo dataset is gated and no HF credential exists here; it was
not downloaded. A compatible 52-joint template was extracted from the author's
public `data/Standard Run.fbx`, removing end bones and animation only. No joint
positions were edited. This template and demo assets are not redistributed.

## Results: distinguish execution from quality

- Initial raw Xiaoman inference completed in **20.82s**, binding **9.77s**, whole core
  operation **38.39s**. 52 predicted bones; bound 725981 original Blender vertices,
  no decimation/welding, mapping error 0. Export retained mean **97.787%** top-four
  weight mass. But hand prediction/weights were wrong around hair/head. That raw
  candidate is rejected diagnostic evidence, not an accepted character.
- The author-provided Bunny control's joint positions were substantially coherent;
  xiaoman seed0 remained poor. This is evidence consistent with a case/domain
  limitation; it does not prove a universal cause for every failure.
- A separate real integration bug was reproduced: modern trimesh sampling used OS
  entropy independently of np.random.seed, so same configured seed yielded different
  points. `sampling-before.log` contains the failed reproducibility assertion.
  Added explicit Generator seeding; `sampling-after.log` passes.
- Final Xiaoman seeded A/B trials have **byte-identical skeleton, coarse-joint and
  fit reports**. Both fail the 3%-extent wrist continuity gate (max **3.769%**),
  and neither exports a GLB. See `tasks/xiaoman-seeded-{a,b}/provenance.json`.
  Final overlay `skeleton-before-after.png`: manual baseline left, rejected seeded
  automatic prediction right. Wrong left-hand/head placement remains apparent.
- Final Bunny control passes: 52 joints, **20026 weighted vertices**, **30000
  triangles**, mapping error0, top-four retained mass **99.654%**. Whole core call
  **7.22s**. Core/MCP repeated inference produces identical skeleton, weights and GLB,
  SHA `385056d790afa794858f66457fe7461da7b2c235eea7628507fe651dc1e5727a`.
  MCP receipts: `mcp-live-fixed-result.json`. The first client harness used the old
  isError property; actual tool succeeded, but the harness failed. The fixed harness
  was rerun and passed; the original log is preserved.

## Motion is external, too

- Author's existing reference clip converted to a skinned reference GLB; no new
  per-frame rotations were authored. Godot4.7.2 RetargetModifier3D transfers poses
  to the automatically predicted control rig. **31 real movie frames** at480x640/
  24fps, Apple M5 compatibility renderer, plus world-pose JSON. Source and target
  rests were compared with Blender; original rest matrix max difference **1.445e-6**.
- Uncorrected motion had actual hand/head intersection; first reported at **frame3**.
  `native-motion-contact.json` and `native-motion-diagnostic.blend` preserve the
  rejection. No raw motion GLB was exported by that gate.
- Deterministic BVH triangle-normal steering plus **Blender native two-bone IK**
  adjusts wrist targets, then bakes the evaluated poses. Prototype had **14 target
  updates**, zero checked intersections across31 frames×2 pairs; minimum checked
  vertex-surface distance **0.00532119**. No manual key angles/positions were supplied.
- Actual shared-core CLI `retarget` reproduced this route. GLB import bone-axis
  differences are handled by a rest-relative per-bone correction, without changing
  the original source. Clean candidate: `tasks/bunny-motion-clean/artifacts/`.
- Export inspection caught an unused raw action leaking into the first candidate.
  It is retained as failed evidence. Worker now removes unused actions/NLA tracks;
  core refuses multiple clips. Final GLB has only **NativeRetargetIKContactTrial**.
- Reimported the **final exported GLB** and reran all31-frame contact checks:
  `core-motion-export-contact.json` reports pass. Sixteen actual Cycles sampled
  frames, side view and GIF are under `core-motion-preview/`. Final animated GLB
  SHA `4f66ab82941ac8e12a12469f3ad81b87ee08778997906309ff44fb197c386191`;
  actual CLI/MCP outputs are identical. `motion-mcp-result.json` records the
  successful real `figura_retarget` call (12 tools discovered). Reimported minimum
  checked vertex clearance **0.00532214**, zero checked surface intersections.

This is an experimental motion-transfer/contact-correction chain, **not** a natural
walk-cycle or full physical simulation claim. No ground-contact, full-body,
continuous-time, watertight containment or garment-layer guarantee. Region membership
uses dominant skin groups and excludes transition triangles. Original Xiaoman's
manual baseline remains intact; this neural route has not passed on Xiaoman.
Human visual approval for new outputs remains pending.

## Tool delivery and reproduction

`autorig` / `figura_autorig`, `retarget` / `figura_retarget` share core logic. Models
and graphics libraries are external processes; bare OpenFigura does not import
Torch, NumPy or bpy. Explicit device/seed/query chunk, source/animation/checkpoint
hashes, logs, numeric predictions, diagnostics and failures are recorded.

```sh
# External MIA install already prepared; TASK has a static model.glb.
openfigura autorig TASK --backend mia --device cpu --seed 42 --query-chunk 8192
openfigura retarget TASK --animation REFERENCE.glb --frames 31 --fps 24
openfigura render TASK --artifact model-animated.glb --frame 15
```

Real core scripts: `run_core_complete.py`, `run_seeded.py`, `check_mcp_fixed.py`.
Actual motion CLI command is in `core-motion-clean-result.json` / task provenance.
Separate native reference/motion recordings and prototype scripts are retained.
**73 tests passed** at the final recorded pre-packaging check; tests use fake runtimes
and tiny GLB fixtures, numeric sampler tests skip when NumPy is unavailable.

MIA v2 source was also cloned (`bbd8b158d88879c310ad130f9b25056935d221e9`), **not installed
or inferred**. Its official stack adds Torch2.8/CUDA12.9, xformers and Hunyuan2.1
ShapeVAE; code has CPU branches but this does not establish Mac compatibility.
SkinTokens and MocapAnything source-only reviews are part of the separate
3DGenStudio report. No Windows/CUDA inference was run this turn.
