# Automatic rigging as an external tool

User intent: run a real open-source framework rather than use the agent to place
bones or invent poses per character. Explicit authorization: try the framework,
prefer stable external algorithms and retain OpenFigura as a CLI/MCP tool layer.

Use Make-It-Animatable first: its inference code selects CPU without CUDA;
UniRig's official dependencies include CUDA spconv and are not the first Mac test.
Use an isolated Python 3.11 environment under its external source checkout; keep
OpenFigura's stdlib core free of torch/bpy imports. Do not blindly execute upstream
setup scripts or install the CUDA requirements on Mac.

Input is the approved static Xiaoman GLB, unchanged. Neural output must include
predicted joint heads/tails, hierarchy, skin weights, original-coordinate transform,
and runtime/source/checkpoint hashes. No manual bone coordinates may be substituted
for a failed neural inference. Preserve input topology/materials when binding.

Only integrate a neural backend after a real inference and Blender reimport check.
Core API `autorig(task, backend, device, seed, query_chunk, artifact)` is mirrored
by CLI/MCP. Device selection is explicit and capability probes report CPU/CUDA/MPS
as tested; do not imply Metal support from general PyTorch availability. Missing
runtime/checkpoints must be unavailable, not a successful stub.

Rigging and animation are distinct: MIA's pose model estimates rest pose, not an
arbitrary walk or gesture. Subsequent motion uses existing externally evaluated
animation/retargeting algorithms and the existing contact gate. No claim of
automatic collision response, cloth simulation or repaired finger geometry.

Licences: code MIT; Hugging Face model metadata says Apache-2.0. Keep templates,
weights and trial outputs external. The Mixamo template dataset has no licence
field in its card; do not redistribute it or motion clips as OpenFigura assets.
Avoid the optional Auto-Rig Pro submodule until its redistribution terms are clear.

Acceptance: source hash unchanged; predicted skeleton finite/nondegenerate; skin
weights finite/nonnegative/normalized; report timing/memory/device; independently
inspect the bound GLB and render neutral/pose evidence. Human visual approval must
remain pending. A capability failure is recorded with the actual error and a
portable GPU run procedure, without claiming a successful local neural result.

## Verified extension after external motion proof (2026-10-08)

Added `retarget`/`figura_retarget` after actually exercising Godot's native
RetargetModifier3D and Blender native two-bone IK/BVH steering. Caller supplies
a skinned reference GLB; no chat-authored keys. Matching Mixamo hand/body names
and one skinned render mesh are required. Integer-frame regional checks gate
export. Raw incompatible/penetrating motion is diagnosed, never silently delivered.
The final exported GLB is reimported and checked; only the corrected clip exists.
This does not promise full cloth, continuous-time or natural walk-cycle quality.
