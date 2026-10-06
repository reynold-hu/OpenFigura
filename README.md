<p align="center">
  <img src="assets/logo-wordmark.png" alt="OpenFigura" width="520"/>
</p>

**OpenFigura is a local, agent-driven 3D asset production framework.**
Drop in a reference image and a plain-language brief; get back a textured
GLB, a Blender-checkable scene, multi-view renders, and a provenance record
that says exactly how every artifact was made.

> **Agent users:** the manual is [`docs/usage.md`](docs/usage.md) — or
> register the MCP server (`openfigura-mcp`) and let `figura_*` tools
> self-describe.
>
> **No reference art yet?** [`docs/input-guide.md`](docs/input-guide.md)
> has copy-paste prompts for GPT Image / Seedream / Grok / Midjourney that
> produce OpenFigura-friendly inputs.

It is a *replacement for the paid "upload your art to someone's cloud"
workflow* — Tripo, Meshy and friends — not for any specific tool. The
generation itself comes from swappable open backends (Pixal3D/TRELLIS.2
runtimes, and anything you register later). OpenFigura provides the boring,
valuable parts: a stable tool surface, capability detection, reproducibility
ledgers, and real render-based inspection instead of trusting one pretty
preview.

```
reference image + brief
        │
        ▼
  ┌───────────────┐    backends: pixal3d.cpp, trellis, …   ┌──────────────┐
  │ openfigura-core│ ─────────────────────────────────────▶ │  GLB + PBR   │
  │  (engine)      │    generate → render → inspect → export│              │
  └───────┬───────┘                                         └──────────────┘
          │
   ┌─────────────┬─────────────┐
   ▼              ▼             ▼
 CLI         MCP server    (later: own
 (scripts,   (Codex,       agent loop)
  CI)        opencode,
             Claude…)
```

## vs. commercial platforms

What "平替" (alternative) honestly means here: same *category* of capability,
different *architecture* of trust. Category-level differences, from public
documentation of each service as of 2026-10:

| | OpenFigura | Tripo AI | Meshy AI | Hi3D |
|---|---|---|---|---|
| where generation runs | **your machine** | their cloud | their cloud | their cloud |
| your reference art leaves your PC | never | yes (upload) | yes (upload) | yes (upload) |
| pricing | free (AGPL); you pay electricity | credits/subscription | credits/subscription | credits/subscription |
| reproducibility | seed + ledger → byte-identical GLB on same host | varies; server-side pipeline opaque | varies | varies |
| audit trail | provenance.json: every command, hash, exit code | platform history | platform history | platform history |
| agent integration | MCP + CLI, tool contracts in this repo | API keys, network required | API keys, network required | API keys, network required |
| output topology/rigging | explicit pipeline (v0.2), retopo/rig are visible steps | automated, opaque | automated, opaque | automated, opaque |

**What we do not claim:** that generation quality matches or beats these
services. The backends we wrap (Pixal3D, TRELLIS.2) are open peers of the
models behind commercial sites, but quality depends on inputs, resolution
and luck-of-the-seed — and we refuse to claim a comparison we haven't run.
The golden suite ([`docs/testing-guide.md`](docs/testing-guide.md)) exists
precisely so same-input comparisons become measurable, not rhetorical.

*Tripo, Meshy and Hi3D are trademarks of their respective owners. This
project is not affiliated with or endorsed by any of them; the table
describes our architecture versus their publicly documented one.*

## Why not just an agent?

Agents (Codex, opencode, Claude Code, `pi`) already schedule tool calls
better than any framework we could ship today. What they lack is a
*local, private, free, inspectable* 3D pipeline with stable tool contracts.
That is exactly the layer OpenFigura is. The MCP server is the primary
interface; a CLI with identical commands exists for scripts and CI, and an
optional self-hosted agent loop may come later — all three share one core.

## Quick start

Full manual for agents and humans: [`docs/usage.md`](docs/usage.md).

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"           # core + CLI
pip install -e ".[mcp]"           # + MCP server

# Register a backend binary (e.g. a prebuilt pixal3d.cpp runtime)
openfigura backends

# Generate → render → inspect → export, one task, one ledger
openfigura generate input.png --backend pixal3d --seed 42 -o out/
openfigura render  out/task.json
openfigura inspect out/task.json
openfigura export  out/task.json --format glb
```

Every run writes `provenance.json`: input SHA-256, exact command line,
backend version, wall time, peak memory, output hashes. If it cannot be
re-run from that file, it is a bug.

## Requirements & honest limits

- Generation backends have their own hardware needs. The Pixal3D Q8 path is
  verified on Apple Silicon (Metal); CPU-only x86 works but is slow —
  local + private + free is the promise, speed is a per-backend property.
- Outputs are dense triangle meshes (~10⁶ tris). Rigging/animation needs
  retopology; OpenFigura tracks that as a post-processing step, it does not
  pretend one-shot generation is game-ready.
- Visual quality is judged by rendered views, not by the generator's own
  preview. That is a design rule, not a disclaimer.

## License

AGPL-3.0-only — code only. **Assets you generate are yours** (output
exemption, Blender-style); backends and model weights carry their own
licenses, which every task's provenance ledger records. See
[`LICENSES.md`](LICENSES.md) and [`TRADEMARK.md`](TRADEMARK.md).
