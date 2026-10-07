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
The OpenFigura adapter remains AGPL-3.0-only. Other surveyed neural pipelines
are not vendored, installed or represented as working backends.
