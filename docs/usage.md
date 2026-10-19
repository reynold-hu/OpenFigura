# OpenFigura usage manual

> **Written for AI agents** (Codex, opencode, Claude Code, pi) and the
> humans pointing at them. Follow the commands literally; where a rule says
> "never", it is protecting a 27-minute GPU run or the integrity of the
> provenance ledger. Humans: hand this file to your agent or register the
> MCP server and let it discover the tools.

## 0. What this tool is

The base workflow has four deterministic verbs over local 3D generators:
`generate` (image → textured GLB), `render` (GLB → neutral multi-view
frames), `inspect` (GLB → structural report), `export` (verified artifacts
+ ledger → delivery folder). You (the agent) supply intent, retries and
judgment; OpenFigura never improvises geometry.

## 1. Install

```sh
git clone https://github.com/reynold-hu/OpenFigura && cd OpenFigura
python3 -m venv .venv && source .venv/bin/activate   # Python ≥ 3.10
pip install -e ".[dev]"        # core + CLI + tests
pip install -e ".[mcp]"        # + MCP server
```

Verify with zero external dependencies:

```sh
python -m pytest tests -q      # must pass on a bare machine
openfigura backends            # honest probe; "unavailable" is a valid answer
```

## 2. Register backends (environment, not code)

| var | meaning | example |
|---|---|---|
| `OPENFIGURA_PIXAL_RUNTIME` | path to pixal3d.cpp binary | `~/tools/pixal/trellis-cli` (Windows: `.exe`) |
| `OPENFIGURA_PIXAL_MODELS` | directory of verified weights | `~/tools/pixal/models-sv` |
| `blender` | must be on PATH or `/Applications/Blender.app` | brew/apt/installer |

The runtime ships per-OS builds (Metal on macOS, CUDA on Windows/Linux);
the env-var interface is identical. If your `OPENFIGURA_PIXAL_MODELS`
contains `birefnet.gguf`, `generate` auto-mattes inputs that lack a real
alpha channel with BiRefNet before the SV flow (threshold fallback without
it, which damages specular highlights).

`openfigura backends` reports what was found and why anything wasn't.
Do not proceed past `available: false` by editing code — fix discovery.

## 3. The one workflow that matters

```sh
# 1. Check the input BEFORE spending a long run
openfigura preflight ref.png
#    errors  => stop; crop to one view / matte / upscale is NOT a fix,
#               re-source the image. See docs/input-quality.md.
#    warnings => decide consciously; record your reasoning to the user.
#    `symmetry` reports a mirror-IoU of the PNG alpha silhouette when the
#    file decodes (JPEG/no-alpha/oversized report status=unavailable with a
#    reason, never a guess). Advisory: `asymmetric` adds a warning, not an
#    error. Thresholds are OpenFigura heuristics (see core/symmetry.py).
#    `--face` adds the optional MediaPipe check (~5 s; face extra + model):
#    estimated face pixels at 1024 res and border cropping. Stylized/profile
#    art may report no_face; that is not an error.
#    Human needs a good source image? Point them at docs/input-guide.md
#    (ready-to-paste prompts for commercial text-to-image models).

# 2. Create the task and stage the image
openfigura new ref.png -o tasks/ --name hero-idle
#    -> prints task root, e.g. tasks/hero-idle

# 3. Generate (LONG: minutes to ~30 min depending on hardware; use a
#    generous timeout, never kill-and-fake)
openfigura generate tasks/hero-idle --backend pixal3d --seed 42
#    If the input has no real alpha matte, the backend's preprocess step
#    runs first (BiRefNet cutout -> artifacts/matte_cutout.png), recorded
#    as its own `preprocess` ledger entry; the cutout is what generates.
#    Pass `matte: off` via params only if the input is already matted.

# 3a. Preview first when the run is expensive or the input is uncertain
openfigura generate tasks/hero-idle --backend pixal3d --dry-run
#    Read-only: preflight verdict, conditional matte step, generate step,
#    effective params, credits=0, and honest "wall time uncalibrated".
#    No ledger entry, no artifacts, no backend process. `force` and
#    unavailable backends are shown as would-refuse/would-proceed, not run.

# 4. Structural truth
openfigura inspect tasks/hero-idle        # ok:false => do not export

# 5. Neutral renders — the ONLY thing quality is judged on
openfigura render tasks/hero-idle --samples 32
#    Pixal3D output faces +Y: use `--facing 180` for correct front view.
#    New backend? Probe its facing convention once, record it, reuse it.

# 6. Deliver
openfigura export tasks/hero-idle --dest dist/
#    Engine-bound delivery: `--format fbx --fbx-preset godot|unity|unreal|blender`
#    writes an FBX authored for that engine's axes/units. The manifest records
#    the resolved exporter arguments and each preset's verification status
#    (`blender` and `godot` are import-verified on this repo's machines;
#    `unity`/`unreal` are documented conventions — verify in the target engine).
```

Every step appends to `tasks/hero-idle/provenance.json`: command, exit
code, wall time, sha256s, preflight verdict. To reproduce or audit an
asset, read that file — not chat history.

## 4. MCP registration (preferred for agents)

opencode (`opencode.json`):

```json
{ "mcp": { "openfigura": {
  "type": "local",
  "command": ["/ABS/PATH/OpenFigura/.venv/bin/openfigura-mcp"],
  "enabled": true } } }
```

Codex CLI (`~/.codex/config.toml`):

```toml
[mcp_servers.openfigura]
command = "/ABS/PATH/OpenFigura/.venv/bin/openfigura-mcp"
```

Tools: `figura_backends`, `figura_preflight`, `figura_new_task`,
`figura_generate`, `figura_render`, `figura_inspect`, `figura_print_check`,
`figura_export` and the rest of the `figura_*` mirrors. Same contracts as the
CLI; `figura_generate` blocks for the full run — set your tool timeout
accordingly. A bundled agent skill lives at `skills/openfigura/SKILL.md`.

## 5. Rules of engagement

1. **Preflight before every generate.** Never pass `force` without
   telling the human which error you're overriding and why.
2. **`visual_approval` is a human field.** You may report render paths
   and structural stats; you may not declare an asset "good". Show frames,
   let the human decide.
3. **One view per generate call.** Multi-view sheets are four separate
   tasks (or a future multi-view backend mode with real camera params).
4. **Failures are data.** If a step fails, keep the task folder; the
   ledger records the failed command verbatim. Retrying with different
   params is a new generate, not an edit of history.
5. **Seeds are sacred.** Reuse the recorded seed for "the same" asset;
   changing seed = new candidate, new review.
6. **Nothing heavy enters git.** Weights, GLBs and task outputs stay
   out of commits (`.gitignore` enforces; don't fight it).

## 6. Troubleshooting

| symptom | likely cause | action |
|---|---|---|
| `backends` says unavailable | env vars unset / binary not executable | fix discovery; re-probe |
| front render shows the model's back | facing convention | `--facing 180` (Pixal3D) |
| generation killed mid-run | timeout too short | raise timeout; check wall time in ledger |
| export refuses | inspect problems | fix input/backend, regenerate; never hand-copy around the gate |
| renders look flat | you're comparing generator previews | re-read design.md: neutral renders are the gate |

## 7. Going further

- Design rationale: [`design.md`](design.md)
- Input contract: [`input-quality.md`](input-quality.md)
- Regression suite: [`../golden/README.md`](../golden/README.md)
- Working *on* the repo: [`../AGENTS.md`](../AGENTS.md)

## Mesh budgets and use cases

`openfigura presets` / `figura_presets` reads the use-case table
(`game / animation / print / vr_ar / product_display / general`) with each
budget's stated basis — data only, nothing executes. Apply one with:

```sh
openfigura mesh TASK --operation retopo   --use-case game   # target_faces=20000 if unset
openfigura mesh TASK --operation optimize --use-case game   # ratio = 20000/current, computed from the GLB
```

Rules (enforced, tested): explicit `--params` always win; `optimize` derives
its ratio from the source triangle count, never from a guess; `print`/`general`
set no implicit budget; the ledger records the resolved values and which basis
they came from. Use-case defaults apply to `retopo`/`optimize` only and fail
closed elsewhere.

## Printability check

```sh
openfigura print-check TASK --params '{"build_volume_mm": [256, 256, 256]}'
#  -> pass/fail + counts in the report; also writes <task>/print-check.json
```

Measures topology, size and orientation: exact-position welding recovers seams
split by normal/UV, then open boundary edges, non-manifold edges, zero-area
faces, duplicate faces, connected shells, overhang area beyond a configurable
angle, bed-contact area and an optional build-volume fit are counted. Params:
`build_direction` (default `[0,1,0]`), `overhang_angle_deg` (45),
`bed_tolerance_mm` (0.2).

**Wall thickness is optional and external**: set
`OPENFIGURA_PYMESHLAB_PYTHON=/path/to/python-with-pymeshlab` and pass
`"wall_thickness": true` (plus optional `"min_wall_mm": 0.8`). It reports a
shape-diameter proxy in mm — not a calibrated wall measurement — and says
`unavailable` with the reason when the runtime is not configured.

Node transforms are not applied and skinned/morph assets are checked in rest
geometry; both are reported as warnings. Nothing is repaired — a fail means
"look closer or repair elsewhere", never a silent fix. `figura_print_check`
mirrors it.

## Scorecard

```sh
openfigura score TASK
openfigura score TASK --params '{"profile": "print", "build_volume_mm": [256,256,256], "face": true}'
```

Deterministic 0-100 readiness score over five sub-scores (structure, evidence,
input, printability, delivery) with transparent formulas; writes
`<task>/scorecard.json` and ledger entry `score`. It answers "what is missing
before human review", not "is it beautiful": `human_review` stays pending and
aesthetics belong to the rubric. `figura_score` mirrors it.

## Final evaluation report

```sh
export OPENFIGURA_GLTF_VALIDATOR_MODULE=/abs/path/node_modules/gltf-validator  # optional
export OPENFIGURA_TRIMESH_PYTHON=/abs/path/venv/bin/python                    # optional
openfigura evaluate TASK
#  -> <task>/evaluation.json + <task>/evaluation-report.md
```

`evaluate` runs the same scorecard, then optional Khronos glTF-Validator
(Apache-2.0) and trimesh (MIT) checks in subprocesses, and writes a
human-handoff report: sub-scores, topology/orientation, input preflight,
external findings, evidence coverage and a pending human checklist. Missing
runtimes are reported `unavailable`; trimesh is skipped above 300k triangles
(`OPENFIGURA_TRIMESH_MAX_FACES`) so the report never hangs. `figura_evaluate`
mirrors it.

## Review, publish, compare

```sh
# A human records the verdict; the runner never infers it.
openfigura review TASK --verdict approved --reviewer "Your Name" --note "ok for v1"
# Publish requires that recorded approval, pins it to the artifact SHA-256,
# and refuses to overwrite an existing published delivery.
openfigura publish TASK --dest dist/published
# Compare candidates structurally; side-by-side renders when Pillow + renders exist.
openfigura compare TASK --artifacts model.glb,model-seed43.glb --views front,side
```

`review` writes `review.json` and a ledger entry and refuses to overwrite an
existing review (use a fresh task for a new verdict). `publish` copies the
approved artifact, `review.json`, renders, provenance and an `export-manifest.json`
whose `approval`/`published` blocks record who approved which bytes.
`compare` writes `compare.json` (SHA-256, bytes, inspection fields) and, when
Pillow and matching renders exist, `compare/<view>.png` composites. Each
candidate also carries `texture` atlas statistics (`dark_fraction`,
`near_white_fraction`, `mean_rgb`, size, sha) explicitly labelled a **proxy**:
they surface "this seed painted no dark brow/iris pigment" without pretending
to be a quality verdict. MCP mirrors:
`figura_review`, `figura_publish`, `figura_compare`.

## Texture refinement and experimental rigging

- `refine-texture` / `figura_refine_texture`: calibrated source RGB projection;
  see [texture workflow](texture-refinement.md).
- `rig` / `figura_rig`: experimental basic-human Rigify from explicit bone
  calibration; see [calibration, skin methods and limitations](calibrated-rigging.md).
- Render/inspect/export accept `artifact` to select a separate candidate. Render
  accepts `frame` for pose checks. Human visual approval remains separate.

## External rigging and motion

`openfigura autorig TASK --backend mia --device cpu --seed 42 --query-chunk 8192`
invokes an installed external MIA v1 runtime. `figura_autorig` exposes the same
arguments. Failed continuity checks never fall back to manually fitted coordinates.

`openfigura retarget TASK --animation SOURCE.glb --artifact model-autorig.glb
--frames 31 --fps 24` uses native Godot and Blender algorithms. `figura_retarget`
mirrors it; output is an independent `model-animated.glb`. Matching Mixamo bone
names/hand groups required; failures and residual contacts refuse export.
Only the corrected clip is delivered. Source GLBs stay unchanged.
See `docs/neural-rigging.md` for installation, scope and actual limitations.
