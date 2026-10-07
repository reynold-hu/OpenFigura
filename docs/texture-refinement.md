# Calibrated texture refinement

`refine-texture` / `figura_refine_texture` share `core.engine.refine_texture`.
This is source-image projection into an existing UV atlas, not neural geometry
refinement or physical albedo recovery. No GPU or neural weight download is required.

Install the optional image dependencies in your project environment:

```sh
pip install 'openfigura[detail]'
openfigura refine-texture TASK --views-dir CALIBRATED_VIEWS --roi-mask ROI.png --strength 1
openfigura inspect TASK --artifact model-refined.glb
openfigura render TASK --artifact model-refined.glb --facing 180
openfigura export TASK --artifact model-refined.glb --dest DELIVERY
```

References: `transforms.json` with `camera_angle_x`, positive `mesh_scale`,
`frames[].file_path`, and rigid right-handed 4x4 `transform_matrix`, plus
pre-matted RGBA images. Pixal's native `artifacts/model.svviews/` is a starting
point. Do not recrop a view without updating its calibration. A single optional
grayscale ROI mask must have the same dimensions as every frame. White permits
projection, black protects the existing texture. Multi-view input needs genuinely
consistent cameras and subject appearance; crop zooms are not automatically valid
views. `strength` is finite in [0,1].

The input GLB must have a single triangle primitive, one material with an embedded
BaseColor image, non-interleaved vertex buffers and no node transforms (the current
Pixal output meets this contract). General GLB scenes are intentionally refused.
This inherited limitation is part of the backend contract, not general glTF support.

Original `model.glb` is preserved. The candidate is `model-refined.glb`, with a
`.trust.png` map and ledger containing input/reference/mask/output hashes, strength,
wall time, upstream revision, geometry/material-buffer invariants and limitations.
Reference images/cameras are copied into the task for replay. Existing candidates
or staged reference directories are refused; use a fresh task to keep evidence.
Candidate renders live in `render/model-refined/`, separate from original frames.

Global colour matching is disabled: no reference view should recolour unseen
surfaces. Even trusted pixels may carry source lighting or align to the wrong
semantic part. Inspect edges, grazing angles, overlaps and all four views. Geometry,
hand/finger separation and physically correct roughness are not repaired.

Vendored projection code: image-to-3dlab, Apache-2.0, pinned commit in
`third_party/image-to-3dlab/SOURCE.md`; LICENSE/NOTICE also ship in the wheel.
The OpenFigura adapter remains AGPL-3.0-only. Five research checkouts and exact
revisions are recorded in `docs/upstream-source-manifest.json`.
