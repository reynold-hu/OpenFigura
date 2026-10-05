# Progress log

Facts only, newest first. Each entry names the command or artifact that
proves it. Intentions live in `ROADMAP.md`, not here.

## 2026-10-05 — input contract + golden-case harness

- **Preflight landed as a gate, not prose**: `core/preflight.py` runs
  stdlib PNG/JPEG header checks; `engine.generate` refuses on errors and
  records every check in the ledger; CLI (`openfigura preflight`) and MCP
  (`figura_preflight`) expose it. Rules in `docs/input-quality.md`
  (≥512px hard floor, ≥1024px recommended, sheet-aspect warning, PNG-over-
  JPEG, matte-damage lessons from the 2026-10-05 trial).
- **Golden-case format + runner** (`golden/README.md`,
  `scripts/run_golden.py`): input+case.json committed, baselines promoted
  only by humans, `--emit-candidates` for review, strict-hash optional
  because same-seed reproducibility is machine-dependent. First real case
  awaits user-supplied images.
- 15/15 tests green (7 new preflight tests on synthetic stdlib-built
  images; engine tests updated to stage valid PNGs, which is exactly the
  gate doing its job — the old fake `b"\x89PNG fake"` input now refuses
  to generate).

## 2026-10-05 — v0.1 tool layer lands

- **MCP server verified over real stdio**: spawned `openfigura-mcp`,
  `initialize` → `tools/list` (6 tools) → `tools/call figura_backends`
  returned live probe results (blender: available). mcp 2.3.0; dual import
  shim for mcp 1.x (`MCPServer`/`FastMCP`).
- **CLI verified end-to-end on a real asset**: task workspace → structural
  inspection of the 972,414-triangle Pixal3D GLB (PBR refs, UV, normals
  all pass) → 4 auto-framed Cycles renders → export with manifest; GLB
  sha256 `f0c2798f…48bd57` matches the tarotist-xiaoman source artifact.
- **Blender render backend fixes found by smoke, not by reading**:
  Blender 5.2 subprocess drops custom env vars (config passed via file +
  argv after `--`); `Vector.rotate` needs a Matrix; glTF importer models
  face +Y (`--facing 180` corrects Pixal3D output). All three were silent
  or ugly failures before the real run.
- **8/8 tests green** (`python -m pytest tests -q`): fake-backend
  generate→inspect→export, export refusal on broken GLB, pixal3d
  discovery/capability/command-shape (command pinned to the invocation
  proven in tarotist-xiaoman `loop/logs/2026-10-05-pixal-local-trial.md`).
- Licensing landed: AGPL-3.0 + output exemption (`LICENSES.md`),
  `TRADEMARK.md`, `NOTICE`, DCO-based `CONTRIBUTING.md`.

## 2026-10-05 — upstream facts this design stands on

- **Pixal3D local generation is real**: Apple M5 / 16GB, Metal runtime
  `v0.10.1-desktop-alpha`, weights `raven38/pixal3d-sv-q8_0-v1` (9/9 sha256
  verified), seed 42, res 1024 → textured GLB in 27m15s. Evidence, command
  line, memory figures and known defects (eye highlights, occluded ears,
  foot flakes): `tarotist-xiaoman/art/experiments/2026-10-05-pixal-local/`
  and its loop log. User aesthetic verdict on the result: approved
  ("效果非常好"), which is what motivated this project.
- **What the LLM did in that run**: assembled one CLI command. The quality
  came from the dedicated 3D model, not from the agent — the founding
  premise of this tool layer.
- **Hand-written Blender geometry (v4 route) is the ceiling of the
  LLM-models-directly approach**: complete and controllable, but visibly
  below generator fidelity on face/hair — do not rebuild that as a product.

## Known gaps / honest limits

- `figura_generate` has not yet run a *real* generation through
  OpenFigura itself (only the borrowed artifact; the command builder is
  unit-tested against the proven invocation). First real run is v0.2 item 0.
- Facing/up-axis conventions exist only for pixal3d; other backends TBD.
- No retopo/rig/skin/animate verbs yet — the entire "make it move" line is
  v0.2 and unproven in-repo.
- No CI yet; tests run locally under `.venv` (Python 3.14).
- Visual approval is never recorded as pass by agents; `visual_approval`
  in ledgers stays `pending` until the user says otherwise.
