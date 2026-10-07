# Rigify motion proof — 2026-10-07

Evidence root: `~/Desktop/openfigura-rig-trial-2026-10-07/`.
Original: accepted chibi GLB, SHA
`f0c2798f676cd611782f746d8807816d283f06d84397fa04eae4ab443448bd57`.
Source file hash checked unchanged after all trials. No edits to the Tarotist game.

## Observed failures

- Basic Rigify generated 222 bones, but Bone Heat on a decimated imported mesh gave
  0/112861 weighted vertices; the welded/decimated retry gave 0/18213.
- Approximate weights made the low-poly candidate move, but neutral appearance was
  badly damaged. The candidate is retained only as failed evidence, not a baseline.
- Actual default core adapter on original high-poly also failed Bone Heat:
  0/725981 vertices, exit 1, no fallback or GLB. See
  `automatic-skin-check/provenance.json` and artifact log tails.
- Imported skin creates an invisible Icosphere bone-display helper. Its object
  hide_render flag alone is insufficient: its collection is not visible. Camera
  framing originally included it. Renderable-mesh filtering now excludes these
  helpers; regression tests cover both direct and collection visibility.

## Functional candidate, still experimental

Explicit capsule weights plus manually calibrated head region, **no welding or
simplification**. Rigify metarig bone coordinates are a fixture-specific manual
calibration, not inferred by a neural model. Finger chains are absent.

- Core operation output: `core-rig/artifacts/model-rigged.glb`, SHA
  `11c9c64df5cf0deb57dd47030efed611049bd6961526712f669956d47f4a5499`.
- 972414 triangles, 725981 weighted vertices, 35 exported deform joints,
  `CalibrationWave` 30-frame clip (FK arm/head/leg keys).
- Native binding 7.06s; actual command/calibration/hash/method in task provenance.
- Reimported the **exported GLB**, evaluated vertex motion at frame15:
  max delta 0.20876 world units, character height 0.88679. This proves movement,
  not natural anatomy or clean contacts. 15 sampled Cycles frames plus side pose.
- Core renderer checks frame15 through the real CLI with the same frame1 camera
  bounds; source helper geometry excluded. Four views per pose.
- Separate Godot preview imported the GLB and played `CalibrationWave`. MovieMaker
  recorded 31 real frames at 480x640/24fps with Apple M5 OpenGL compatibility.
  Rest/motion images differ. No animation was installed into the 2D game entry.

## Outputs and limits

- `core-rig/motion-proof.gif` / `.mp4`: Blender reimport playback.
- `godot-preview/godot-motion-proof.mp4`: actual game-engine playback.
- `core-rig/artifacts/model-rigged.blend`: editable metarig/control rig.
- `core-rig/artifacts/model-rigged.glb`: exported skin + clip.
- `calibrated-clip.json`: exact bone calibration, rigid head region and FK keys.

The animation is a small gesture/step proof, not a validated walk cycle. Hand shape,
cloth intersection, joint volume and ground contact remain quality issues. Capsule
weights do not understand garment boundaries. Human visual approval is pending.
No claim of production rigging, automatic finger repair, or Tripo parity.
