# Hand/garment contact correction — 2026-10-07

The user rejected the original gesture because the hand penetrated clothing.
Movement and skin coverage were insufficient acceptance criteria. This corrects
that omission; the old motion proof is not an approved animation.

Evidence root: `~/Desktop/openfigura-contact-fix-2026-10-07/`.
Reproduce core checks with `.venv/bin/python <evidence-root>/run_core.py` using fresh
output directories. `core.log`, task provenance and `.contact-report.json` files
record the actual operations. `check_export.py` separately reimports exported GLB;
`exported-contact.log` and `exported-contact-report.json` record its verification.

## Root cause and controlled correction

The preset rotated the upper arm toward the torso; nearest-segment skin weights
and FK keys had no contact constraint. A physics collider was not present, and
adding one alone would not correct these directly authored deform poses.

Dominant-weight hand surface versus torso/leg garment surface BVH checks reproduced
intersection on integer frames **8–23**. Frame 15 had **1,448** overlapping triangle
pairs; peak across the full clip was **2,520**. Rest frame was clear. Counts are
triangle pairs, not penetrating vertex counts or collision depth.

Changed only the upper-arm midpoint Z rotation from **−0.5 to +0.5 radians**;
forearm, head, leg, mesh, textures and weights are unchanged. This is an explicitly
corrected outward gesture, not an automatic collision response algorithm.

- Original track with checks: refused at frame 8, no GLB/Blend exported.
- Corrected native rig: **30 integer frames × 2 hand/body region pairs**, no triangle
  intersections; minimum A-vertex to B-surface distance **0.02694814** world units.
  Native operation **18.55s**, including binding, contact evaluation and export.
- Exported GLB reimport: same 60 checks passed; minimum vertex-surface distance
  **0.02701126** world units, zero intersections. This is about 3% of model height,
  not a physical centimetre claim.
- Source SHA remains `f0c2798f676cd611782f746d8807816d283f06d84397fa04eae4ab443448bd57`.
  Corrected GLB SHA `285547a87387fdb9b25e7994419c24ff90131a7b92a1e284d45f084b2f324e87`.
- Reimported corrected GLB: 15 sampled Cycles frames plus frame15 side render.
  `contact-before-after.gif`: original left, corrected right. Render logs under
  `render/`; no image-generation replacement was used.
- **55 tests passed**: `.venv/bin/python -m pytest tests -q`. Tests cover crossing
  at intermediate frames, clearance, empty/invalid regions, unchecked adapter
  results and refusal to animate without contact configuration.

## Export contract and limits

`contact_checks` in calibration names explicit deform-group regions and a margin.
Any surface intersection or insufficient checked vertex clearance blocks export.
Empty regions fail. Animated rigging now requires this configuration. CLI and MCP
use the same core gate. Static rigs without regions report contact unavailable.

Region membership uses each vertex's dominant deform group; only triangles whose
three vertices belong to a region are included. This excludes transition faces
near wrists/shoulders. The test does **not** prove closed-volume containment,
continuous-time nonpenetration, full-body self collision, sleeve/arm clearance,
finger contact, joint volume, ground contact, or cloth dynamics. The generated
mesh is not a clean semantic separation of skin and garment layers. Further
movement needs its own checks and visual inspection; do not generalize this result
to walking or arbitrary motions. Human visual approval remains pending.

`xiaoman-basic-v1.json` retains the old rejected motion with an added gate for
reproducible failure. `xiaoman-contact-v2.json` supplies the corrected tested track.
