# 3D-generation IDE/workspace landscape and aigccat review — 2026-10-19

Public-source survey. No vendor code was copied, no non-public implementation was
used, and nothing here claims parity. Sources are public pages/repos and the
public API schemas shipped with local ComfyUI 0.22.2. REA evidence IDs are
listed where REA was used.

## aigccat (github.com/RainNameless/aigccat, Apache-2.0)

**What it is (observed from the public README/docs).** A self-hosted AI 3D asset
pipeline: natural language or image → 3D, then texturing, topology, UV, rigging,
animation, versioning, QA, and Unity/Godot delivery. Architecture: Rust/axum
backend, framework-free HTML/JS frontend with local Three.js, MinIO as the asset
store, Blender 5.2 inside the amd64 container, OpenCode bridged to Blender for
AI-written rigging scripts, and an MCP channel with 17 tools. It ships an
11-tool workbench, an asset library and a five-level asset graph.

**Ideas worth referencing (design, not code):**
1. **Engine pack contract** — GLB + asset contract + outline + manifest per
   engine. Our `export --format` + presets cover the file side; an explicit
   machine-readable delivery manifest is the missing piece.
2. **Version three-state** `latest / approved / published`, with published
   locked and one-click rollback, on an append-only history tree. Our ledger is
   append-only but has no approval/publish state — `visual_approval` is a field,
   not a gate.
3. **Job vs asset separation** and candidate batches with anchors — close to our
   task + stage-attempt model; the explicit "candidate batch" concept is useful
   when several seeds compete.
4. **Cost ledger + budget circuit breaker** — our `generate --dry-run` already
   reports `credits: 0`; adding a caller budget cap would make it enforceable.
5. **QA multi-view render sets and side-by-side version comparison** — we render
   frames but do not compare two candidates programmatically.
6. **Honesty rule**: "没跑通就不写支持" — identical in spirit to our ledger law.
   Their public status page admits Tripo API was never validated and
   Meshy/Rodin/Hunyuan3D/Hi3D transports are unverified.

**What we should NOT adopt:**
- Their **Studio web-session runner** logs into the user's paid web subscription
  inside a containerized Chromium and calls the web endpoints. That crosses a
  credential/ToS boundary and contradicts our local/API-first, no-bypass stance.
- Their Rust/MinIO/container stack and UI code as-is: different architecture and
  a large surface; any reuse would need a deliberate licence/benefit review, not
  a copy.
- Their single-user, concurrency-1, no-tenant-isolation model is a known limit
  they state; we should not present it as a multi-user design.

## Landscape: where 3D generation actually runs (public, 2026-10)

| Category | Products (public) | What they expose |
|---|---|---|
| Cloud workspace | Tripo Studio, Meshy (Meshy 7), Rodin/Hyper3D, Hitem3D, 3D AI Studio, CSM, Kaedim, Alpha3D, Sloyd | text/image/multi-view → model, texture, remesh, rig/animate; credits |
| DCC plugin | Meshy for Blender (4.2.6+, Pro+), Meshy Unity/Unreal plugins, Tripo Blender plugin | one-click import into the DCC; keeps materials/textures |
| Local node IDE | ComfyUI 0.22.2 | Load3D/Preview3D/SaveGLB, Stable3D; API nodes for Meshy/Tripo/Hunyuan3D/Rodin |
| Self-hosted pipeline | aigccat | workspace + asset store + MCP, but paid upstream accounts |

Observed differentiators from public pages: Meshy emphasises speed, texturing
and integrations; Tripo emphasises clean topology and API-first workflows;
Rodin/Hyper3D emphasises PBR/visual quality; Hitem3D advertises 1536³ geometry
and print-first output; 3D AI Studio positions as a workflow layer (generation +
texturing + remesh + repair + conversion). These are vendor claims unless
measured; we have not measured them.

**Gap we can own:** none of these is a *local, agent-callable, provenance-ledgered*
3D tool layer. ComfyUI is a local node IDE for humans; aigccat is a local
workspace but depends on paid web/API accounts; the cloud products are not
local. OpenFigura's lane remains MCP + CLI over one engine with a re-runnable
ledger, not a GUI.

## REA deep-dive attempts (2026-10-19)

- **Tripo (www.tripo3d.ai): blocked by Cloudflare Turnstile.** Headless capture
  retained only challenge endpoints (`/cdn-cgi/challenge-platform/...`,
  `challenges.cloudflare.com/turnstile/...`), no application bundle. Evidence
  `ev_5983bc69aca48d16deecac085f2718b2c5d87d203432f99d895f468875cf91b9`.
  We did not attempt to bypass the challenge.
- **Meshy (www.meshy.ai): partially captured.** The public Next.js app loaded
  without a challenge; 328 network events retained (231 script events), 143
  script bodies declared but only **9 JavaScript files (773,748 bytes)** had
  usable bytes after allocation limits. Static analysis of those 9 chunks found
  0 routes and 0 endpoints — **inconclusive**, not evidence of absence.
  Evidence `ev_d36fb95ee0103a111f2f6339d92ab4b0189faafe8335c272aeeb71982369e3b7`
  (capture), `ev_19d149e47858a038ba6e022d4fd60efb6d8ba4f02868dc146f4b234a51167058`
  (script export), `ev_c4d5b4c777ce6687cf36bd665ff0dda92d250b8f84cfaaabb5dfb0cc7c2c897a`
  (analysis, partial).
- The actionable mechanism evidence remains the **public API contracts** already
  recorded in `docs/2026-10-18-3d-product-mechanism-survey.md` (Meshy/Tripo/
  Hunyuan3D schemas shipped with ComfyUI).

## Design implications for OpenFigura (our own implementation)

1. Add a **delivery manifest** to `export` (files + hashes + engine preset +
   contract version), mirroring the useful part of aigccat's engine pack.
2. Introduce an explicit **approval/publish state** for candidates on top of the
   append-only ledger (human-only transitions; published is immutable).
3. Extend dry-run's `credits: 0` into an optional **budget cap** that refuses
   before a paid call.
4. Add **candidate comparison** (same camera, side-by-side) for renders — we
   already have the frames.
5. Keep **part split / UV / smart topology / rig / animate** as separate verbs
   (already the direction; Hunyuan3D's public schema does the same).
6. Do not adopt web-session scraping or containerized paid-account login.

## Limits of this survey

Product claims are public statements, not measurements. Meshy's bundle analysis
is partial (9 of 143 scripts, 0 endpoints). Tripo's app bundle was not reachable
without solving an access challenge. The landscape changes monthly; the date and
sources above bound the claims.
