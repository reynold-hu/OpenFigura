# External neural rigging implementation plan

**Goal:** Replace per-character agent bone coordinates with real framework inference.
**Architecture:** External MIA runtime/checkpoints → schema-checked numeric result →
Blender binding preserving source geometry → common inspect/contact/render tools.
**Tech stack:** Python 3.11, PyTorch 2.1.2 CPU, torch-cluster FPS, PyTorch3D transforms,
MIA PCAE checkpoints, external Blender; stdlib OpenFigura adapter.

- [x] Read current rig engine, upstream source/requirements and licence metadata.
- [x] Resolve official Mac install incompatibilities in an isolated environment;
  record the CUDA requirement failure, then test CPU torch/cluster/PyTorch3D imports.
- [x] Download pinned coarse/joint/weight checkpoints and required template files;
  verify published LFS SHA/size and record local hashes.
- [x] Run a headless real Xiaoman inference with upstream modules and deterministic
  sampling, original-coordinate inversion, explicit CPU device and bounded chunks.
  Preserve raw numeric results and timing/error logs on Desktop.
- [x] Validate neural skeleton/weights before writing a static skin candidate;
  preserve original mesh/material buffers and render/reimport the candidate.
- [x] If inference succeeds, test a stdlib adapter with fake runtime outputs for
  unavailable runtime, invalid weights/shape, source preservation, command args,
  no manual fallback and CLI/MCP parity; observe failure before implementation.
- [x] Run new adapter on actual case, inspect/render; update PROGRESS and usage with
  exact evidence and remaining movement/contact limits. Commit only verified work.

Execute inline in this session; no new agent thread is needed. User already
requested the trial, so routine dependency/environment choices proceed without
another approval gate. The Windows GPU connection question remains optional.

## Final scope/evidence

MIA v1 used on CPU; Xiaoman rejected after deterministic fit checks, Bunny control
accepted only technically. Added a second external motion tool after native Godot
retarget/Blender IK experiments actually passed regional contact checks. CLI/MCP,
73 tests and real receipts are documented in 2026-10-08-neural-rig-trial.md.
A failed character never receives a silently substituted manual skeleton.
3DGenStudio's additional stacks were reviewed separately; no restricted code copied.
