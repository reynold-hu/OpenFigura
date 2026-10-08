# External algorithm rigging and motion tools

OpenFigura does not ask a language model to supply bone coordinates or animation
keys. It invokes optional external runtimes and records their outputs/failures.

```sh
openfigura autorig TASK --backend mia --device cpu --seed 42 --query-chunk 8192
openfigura retarget TASK --animation REFERENCE_SKINNED.glb --artifact model-autorig.glb --frames 31 --fps 24
openfigura render TASK --artifact model-animated.glb --frame 15
```

MCP mirrors: `figura_autorig`, `figura_retarget`. Rigging creates an independent
`model-autorig.glb/.blend`; motion creates `model-animated.glb/.blend`. Originals
are unchanged. Models, environments, source/target animation files and weights
stay outside git. Neither verb synthesizes arbitrary motion from natural language.

## MIA v1 runtime

Set `OPENFIGURA_MIA_HOME` to the separately installed Make-It-Animatable source;
`OPENFIGURA_MIA_PYTHON` optionally selects its Python. Default discovery checks
`.venv-mac/bin/python`, `.venv/bin/python`, `.venv/Scripts/python.exe` under that
source folder. This adapter uses **v1**, not the newer Hunyuan-backed v2 branch.

Verified on M5: Python3.11.15, torch2.1.2, torchvision0.16.2, numpy1.26.4,
trimesh5.1.1, bpy4.3.0, torch-cluster1.6.3 CPU, PyTorch3D0.7.7 pure transforms,
SciPy1.17.1, shapely2.2.0. Torch-cluster needs a compiled FPS extension. PyTorch3D
was installed with `PYTORCH3D_NO_EXTENSION=1`; **only transforms are used/tested**,
not its compiled mesh operators. On this current Clang, old Torch headers required
`CFLAGS=-Wno-invalid-specialization CXXFLAGS=-Wno-invalid-specialization`; old
Torch build code also required setuptools<81. These adjustments were confined to
the external environment, not the system or OpenFigura core.

Required checkpoints: `output/best/new/{joints_coarse,joints,bw}.pth` and a compatible
52-joint `data/Mixamo/bones.fbx`. Source/license/revisions/hashes and the locally
derived public-example template are recorded in the trial report. The gated Mixamo
dataset was not downloaded; no account or licence gate was bypassed.

The worker follows coarse localization → hips normalization → hand-aware surface
sampling → detailed joints → neural weights → inverse coordinate transform. It
caches the upstream encoder across bounded vertex query chunks. Explicit seeded
trimesh Generator sampling fixes a real modern-dependency reproducibility issue.
No manual coordinate/capsule fallback is applied. A 3%-of-model-extent elbow/wrist/
knee endpoint continuity gate blocks detached predictions; **this is not a full
anatomical guarantee**. Source topology/materials are retained by Blender binding;
nearest-point transfer must map back within 0.01% of model extent. Export keeps top
four influences, normalizes them and records retained mass.

CPU is actually tested. CUDA is an explicit selector but has not been run on the
user's Windows machine; the external Torch/FPS build must support its GPU. MPS is
unverified and rejected. Small hands, hair, fused geometry, nonhumanoids and unusual
proportions can fail. No finger-geometry repair is promised.

## Native motion runtime

Requires separate Godot/Blender executables (`OPENFIGURA_GODOT_BIN` can override
Godot). Tested: Godot4.7.2, Blender5.2.2. Target currently requires one skinned render mesh (multiple meshes fail explicitly).
Input animation is a skinned GLB with a
clip and bone names matching the target; the first non-RESET clip is used. Matching
names does not replace cross-skeleton semantic mapping. Current contact/IK regions
require Mixamo left/right hand/forearm/arm names and humanoid body groups.

Godot RetargetModifier3D transfers rotation relative to different rests; position
and scale copying are disabled. Bone world poses are recorded and converted back
to Blender with per-bone axis correction for importer differences. Native two-bone
IK and intersected-triangle normal steering adjust hand targets. No hand-authored
angles/positions/keys are supplied. The resulting keys are baked by algorithms.

Export requires all requested integer-frame regional hand/body intersection and
vertex-clearance checks to pass. Ambiguous normals, missing regions, failed IK or
residual contacts fail explicitly. Only the corrected clip is exported; raw clips
are removed and multiple output clips are refused. Failures keep diagnostics;
create a fresh task rather than overwrite them.

Limitations: transition triangles excluded; no watertight containment proof, no
continuous-time check, no full-body/forearm collision coverage, no cloth simulation,
no ground-contact preservation or validated walk-cycle claim. Nearest surface and
IK are not substitutes for anatomy or good topology. Human visual approval stays
pending even when technical/contact gates pass.

Failed tool-owned GLB/Blend candidates are preserved under
`artifacts/rejected/<id>/` with paths recorded as `rejected_artifacts` in the
failure ledger. They are removed from normal delivery filenames, so the regular
export command cannot deliver rejected candidates. Worker diagnostics remain
available for investigation. A reference containing only RESET is rejected as
having no playable motion.
