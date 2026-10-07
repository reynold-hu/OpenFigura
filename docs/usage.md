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

# 4. Structural truth
openfigura inspect tasks/hero-idle        # ok:false => do not export

# 5. Neutral renders — the ONLY thing quality is judged on
openfigura render tasks/hero-idle --samples 32
#    Pixal3D output faces +Y: use `--facing 180` for correct front view.
#    New backend? Probe its facing convention once, record it, reuse it.

# 6. Deliver
openfigura export tasks/hero-idle --dest dist/
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
`figura_generate`, `figura_render`, `figura_inspect`, `figura_export`.
Same contracts as the CLI; `figura_generate` blocks for the full run —
set your tool timeout accordingly.

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

## Texture refinement and experimental rigging

- `refine-texture` / `figura_refine_texture`: calibrated source RGB projection;
  see [texture workflow](texture-refinement.md).
- `rig` / `figura_rig`: experimental basic-human Rigify from explicit bone
  calibration; see [calibration, skin methods and limitations](calibrated-rigging.md).
- Render/inspect/export accept `artifact` to select a separate candidate. Render
  accepts `frame` for pose checks. Human visual approval remains separate.
