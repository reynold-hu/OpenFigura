# Input quality contract

Generation quality is bounded by input quality. The 27-minute run is the
most expensive thing in this pipeline — every rule below exists so it is
never spent on an input that was doomed. `openfigura preflight <image>`
enforces the machine-checkable subset *before* `generate`, and its result
is recorded in every provenance ledger.

## Hard errors (preflight refuses)

| rule | why |
|---|---|
| short edge ≥ 512 px | below the backend's native resolution, most detail is invented, not upscaled |
| aspect ≤ 3.0 | wide strips are not single subjects; backends hallucinate duplicates |
| PNG or JPEG, decodable header | everything else is unsupported |

## Strong requirements (preflight warns; golden cases must justify each warning)

1. **One character, one view per generation.** Multi-view sheets (our own
   4-view reference!) must be cropped to a single view first. Pixal3D's
   single-image path treats the sheet as one object and will fuse four
   figures into one. Four-view *input* is a separate backend mode with
   real camera assumptions — never fake it by cropping sheets ad hoc.
2. **Clean matte with alpha, background removed.** Solid or busy
   backgrounds compete with the subject's silhouette. Matting must keep
   eyes, ears, hair wisps and dark piping on white clothing — these are
   exactly what naive matting eats (verified the hard way on the 2026-10-05
   trial).
3. **Source edge ≥ 1024 px** to match the default `res 1024`; smaller
   sources get upscaled noise.
4. **PNG over JPEG.** JPEG ringing around high-contrast hair/eye edges
   becomes real 3D bumps at 1024 res.
5. **Neutral, near-orthographic pose, full body, consistent lighting.**
   Extreme foreshortening or heavy stylized shadow teaches the generator
   wrong geometry.

## Pixel-level checks (v0.2, behind `vision` extra)

Foreground coverage 20–80%, subject touching frame edges (bad crop),
alpha-edge softness, duplicate-figure detection in sheets. Documented as
pending so no one mistakes "not checked" for "checked and fine".

## For agents

Run `figura_preflight` (MCP) or `openfigura preflight` (CLI) before
staging any user image. If warnings fire, either fix the input (crop,
matte) or present the warnings to the user before spending a long run —
never silently proceed past an error with `force`.
