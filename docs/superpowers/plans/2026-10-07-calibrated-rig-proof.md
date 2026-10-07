# Calibrated Rigify proof implementation plan

> **For agentic workers:** Use executing-plans for inline execution; no delegated agents are needed. Preserve the existing static source and run evidence on Desktop.

**Goal:** Verify an actual skinned, animated GLB from the accepted chibi fixture,
then decide whether the proven path merits a core/CLI/MCP calibrated-rig backend.

**Architecture:** Explicit per-bone calibration supplies a Rigify basic-human
metarig. A separate animation mesh is welded at coincident positions and decimated;
UV loop data stays with the candidate. Bone Heat is attempted and its coverage is
measured; failure is recorded, never replaced by an unlabelled heuristic. Optional
approximate skinning, if tested, must be a different reported method. Original
high-poly GLB remains untouched. No finger repair or neural pose detection claim.

**Tech Stack:** Existing Blender 5.2 Rigify and standard glTF exporter, Python JSON,
stdlib GLB inspection, real pose renders. All outputs on Desktop.

- [x] Probe Rigify with factory-startup and `default_set=True`.
- [x] Read static fixture front render and fit explicit chibi bone coordinates.
- [x] Try basic-human generation and Bone Heat; record zero-weight failure.
- [x] Weld duplicate positions and retry without deleting the first log.
- [x] Measure actual coverage and inspect deformations at rest, bend and step.
- [x] Export GLB, verify skins/joints/animation channels and preserve `.blend`.
- [x] If deformation is acceptable, expose a calibrated rig operation through core,
  then mirrored CLI/MCP, with fake-worker tests first. If not, report the evidence
  and keep it an experimental rig, without claiming an available production backend.

Outcome: automatic Bone Heat remained unsuccessful. An explicitly selected capsule approximation retained original high-poly geometry and produced a real exported clip; it remains experimental, with human visual approval pending. Decimated/welded candidates had serious appearance loss and are not integrated.
