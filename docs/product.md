# OpenFigura product brief

## One sentence

A local, free, inspectable replacement for the paid "upload your reference
art to someone's cloud and get a GLB back" workflow — Tripo, Meshy, and
friends.

## Why this exists

Commercial image-to-3D platforms look like magic but are mostly three
commodities in a trench coat:

1. Open generation models (TRELLIS-family, Hunyuan, Tripo's own OSS
   ancestors) running on rented GPUs,
2. A thin pipeline of matting, framing, cleanup, retopology and rigging,
3. A polished web UI with per-credit billing.

The models are already public. What no one has published is the boring
middle: a stable, reproducible, agent-callable toolchain that turns "here
is a character sheet" into "here is a verified, textured, provenance-
documented asset" *on your own machine, without uploading your unreleased
game art to a third party*.

That middle layer is this project. It is deliberately **not** an agent —
Codex, opencode and Claude Code already exist and are better at
orchestration than anything we could add. OpenFigura is the tool surface
they call: MCP server + CLI over one engine, with a provenance ledger that
makes every claim re-runnable.

## Who it's for

- Indie game developers who cannot (or will not) ship concept art to a
  vendor's servers.
- Agent users who want `figura_generate` to just work, honestly.
- Teams that need asset reproducibility: same input + same seed + recorded
  command = same GLB, months later, in CI.

## Success criteria (falsifiable)

- v0.2: a Pixal3D-generated character passes retopo → rig → skin-check →
  idle/walk, verified in a real Godot frame, with the entire chain recorded
  in one provenance ledger. Tripo charges credits for each of those steps.
- Adoption honesty: we will not claim parity with commercial polish where
  we have none (face/finger topology still needs human work in v0.2 —
  that's stated, not hidden).

## Business-model stance

OpenFigura will not offer a hosted service, will not add telemetry, and
will not accept a contribution that breaks any of those. AGPL is chosen so
that if a vendor *does* wrap it as a service, they publish their server
code. Our moat is the schema (provenance format, backend conformance), not
secrecy — there is nothing secret here, by design.
