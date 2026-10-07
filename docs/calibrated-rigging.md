# Experimental calibrated Rigify binding

This is an inspectable Blender baseline, **not** neural pose detection, general
character autorigging, finger repair or guaranteed game-ready skinning. It creates
a basic-human Rigify skeleton from explicit world-space bone coordinates, binds an
independent candidate, and optionally exports caller-supplied FK animation keys.

```sh
openfigura rig TASK --calibration calibration.json --skin-method automatic
# Explicit alternative for a motion proof when automatic binding fails:
openfigura rig A_FRESH_TASK --calibration calibration.json --skin-method capsule
openfigura inspect A_FRESH_TASK --artifact model-rigged.glb
openfigura render A_FRESH_TASK --artifact model-rigged.glb --frame 15 --facing 180
openfigura export A_FRESH_TASK --artifact model-rigged.glb --dest DELIVERY
```

MCP: `figura_rig(task_root, calibration, skin_method, artifact)` calls the same core.
`figura_render` also accepts `frame`. The camera is based on frame 1 for stable pose
comparison; bone display widgets in hidden collections do not affect framing.

Requirements: Blender with Rigify, a static unskinned GLB, and **all 29** basic-human
metarig bones in the calibration JSON. Head/tail coordinates are finite, nonzero-length,
Blender-world Z-up coordinates, not normalized screen pixels. The worker refuses
missing/extra template bones. Optional `model_sha256` pins a fixture to its source;
wrong-model application is refused. Already-skinned input and existing candidates
are refused; create a fresh task instead of overwriting evidence.

`examples/calibration/xiaoman-basic-v1.json` is fitted **only** to the accepted chibi
GLB with SHA `f0c2798f676cd611782f746d8807816d283f06d84397fa04eae4ab443448bd57`.
It is not appropriate for scifi-stride, realistic adult proportions or another
character. Fitting/calibration must precede binding; OpenFigura does not guess it.

JSON fields:

- `bones`: bone name → `{ "head": [x,y,z], "tail": [x,y,z] }`.
- `head_rigid_min_z`: optional explicit threshold assigning high vertices to the
  head in capsule mode. This is a manually supplied region, not semantic recognition.
- `clip`: optional `{ "name", "frames", "fps", "keyframes" }`; keyframes map
  existing Rigify control names to `[frame, [EulerX,EulerY,EulerZ]]`, radians.
  Frame 1 should be neutral. Unknown controls fail; arbitrary Python is not executed.

`automatic` uses Blender Bone Heat and requires ≥99.9% vertex coverage. Failure is
reported; **no fallback** is applied. `capsule` explicitly uses nearest bone-segment
weights with up to four influences and optional head locking. Capsule weights do
not understand anatomy, cloth layers, contact, muscle volume or finger separation.
All basic-human outputs declare `finger_bones:false`.

The original GLB is retained; no welding, simplification or texture modification is
performed by this stage. Candidate files: `model-rigged.glb`, `model-rigged.blend`,
`.rig-report.json`, config and diagnostic log tails. The task keeps copied calibration
and input/output hashes. The `.blend` contains editable metarig/controls; normal GLB
export carries deform joints and animations. The export verb's delivery is the GLB
plus inspection/provenance/renders; retrieve the `.blend` from the task artifacts.

Technical acceptance: nonzero skin coverage, JOINTS_0/WEIGHTS_0, exported joint list
and optional clips, plus reimport/evaluate the actual GLB. A valid skeleton is not
visual acceptance. Check wrist/elbow/knee collapse, clothing penetration, head/hair
movement and foot contacts in real poses. Do not call capsule results production
quality without that review. The chibi gesture proof still has rough hand geometry
and possible garment/contact issues; it does not establish a successful walk cycle.

Evidence: `~/Desktop/openfigura-rig-trial-2026-10-07/`. Raw and welded/decimated Bone
Heat trials failed. A reduced mesh also lost appearance without a proper texture
bake, so it was abandoned. Preserved high-poly capsule binding produced 35 deform
joints, one 30-frame clip and a real Godot playback, all labelled experimental.

Rigify is Blender's externally installed open-source component; no Rigify source or
neural rigging weights are vendored. UniRig / Make-It-Animatable remain researched
neural alternatives requiring a separately validated environment and weights.
