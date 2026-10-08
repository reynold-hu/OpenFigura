# Licensing policy

## OpenFigura code: AGPL-3.0-only

OpenFigura-authored code in `src/`, `tests/`, and the project's own documentation is
AGPL-3.0-only (see `LICENSE`). AGPL — not GPL — was chosen deliberately:
the failure mode we are protecting against is someone wrapping this repo
as a closed hosted service and selling it, which is exactly the business
model we aim to make unnecessary. AGPL closes that loophole while keeping
local use, forking, and self-hosting completely free.

## Your assets are yours (output exemption)

Files produced *by* OpenFigura — generated GLBs, textures, renders,
retopologized meshes, rigged characters, exported game packages — are **not
derivative works of OpenFigura** and are not covered by AGPL. This follows
the Blender Foundation's position: running a tool does not license its
output. The provenance ledger describes how an asset was made; it does not
claim rights over it.

Two honest caveats:

1. **Backend and weight licenses travel with the pipeline.** If you generate
   with a component whose license restricts commercial output (for example
   DINOv3-derived encoders or region-restricted model families), that
   restriction comes from the component, not from OpenFigura. Check the
   provenance ledger of each asset before shipping it, and keep the recorded
   license texts.
2. **Input rights are yours to verify.** OpenFigura never uploads anything,
   but it also cannot tell you whether you may 3D-print someone else's
   character.

## Attribution expectations (legal floor, community ceiling)

AGPL already requires preserving copyright notices and stating changes.
Beyond the legal floor we ask — per `NOTICE` and `TRADEMARK.md` — that
forks rename themselves and link back when convenient. Neither is an
obligation beyond the license text.

## Contribution model

DCO sign-off (`git commit -s`), no CLA. Copyright stays with each
contributor; because the project is AGPL, no one — including future
maintainers — can take a contribution private. That is the trade we make
to keep the community larger than any single fork.

## Attributed third-party source

`src/openfigura/_vendor/photo_paint.py` remains Apache-2.0, copyright 2026
Bingeljell and image-to-3dlab contributors. It is vendored unchanged from
commit `10e007b1998c5ffed0b09e16d4218c05a1803afb`. LICENSE/NOTICE ship
with the Python package; source provenance is in `third_party/image-to-3dlab/`.
The OpenFigura adapter remains AGPL-3.0-only. Other surveyed generation pipelines are not vendored or represented as working backends.

The optional external Make-It-Animatable v1 adapter is implemented from its
published inference stages. MIT attribution is retained under
`third_party/make-it-animatable/` and ships with the package. Its actual neural
code/checkpoints/template are not bundled. Model metadata declares Apache-2.0
separately; no template or example-animation licence is inferred from the code.
Godot and Blender remain external tools with their own licences.
3DGenStudio itself has a restricted Community License: no project source was
copied into this AGPL repository. See the 2026-10-08 source-review report.

UniMate (Princeton et al., SIGGRAPH Asia 2026) is surveyed as a candidate
motion backend, not vendored: its code is MIT, but its released checkpoints
are CC BY-NC 4.0, so any OpenFigura adapter must be opt-in with the
non-commercial weight licence stated in `capabilities().notes` before it can
be declared available. Nothing from that repository is copied here. See
`docs/2026-10-08-unimate-review.md`.

The high-to-low normal/AO/albedo adapter and UV diagnostics are original
OpenFigura code (AGPL-3.0-only), using an external Blender installation's
Cycles baking API. No Studio baking source is copied; Blender and optional
generation/rigging runtimes retain their own licenses. Baking an asset does
not change its upstream model or texture license.
