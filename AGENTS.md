# Working on OpenFigura

Read first: `docs/product.md` (why), `docs/design.md` (how), `ROADMAP.md`
(intent), `docs/PROGRESS.md` (verified facts). This repo's whole value is
that its records can be trusted; the rules below exist to keep it that way.

## The five laws

1. **Evidence or it didn't happen.** A claim needs the command that
   produced it and where the output lives. "Renders improved" is not a
   sentence this repo accepts. New facts go into `docs/PROGRESS.md` with
   their proof path; intentions go in `ROADMAP.md`. Never edit a past
   PROGRESS entry to make it look better — append a correction.
2. **The ledger never lies.** Steps record what actually ran (exit code,
   wall time, hashes). A step that could not run reports `unavailable`
   with the probe's reason. Never mark `visual_approval` as passed —
   that field belongs to the human.
3. **CLI and MCP are mirrors, never twins.** New verbs land in
   `core/engine.py` first, then both frontends. If they drift, fix by
   deleting frontend logic, not by adding engine logic.
4. **Heavy things are fetched, never committed.** No weights, runtimes,
   GLBs, or task outputs in git (`.gitignore` enforces most). Tests run
   with fake backends and stdlib fixtures — `python -m pytest tests -q`
   must pass on a machine with nothing installed but Python.
5. **License honesty is a feature.** Backends and weights keep their own
   licenses; record them, don't launder them. Code contributions are
   AGPL-3.0-only with DCO sign-off (`git commit -s`). No hosted-service
   telemetry, ever — privacy is the product promise.

## Input quality is checked, not assumed

Before any generation, run preflight (`figura_preflight` / `openfigura
preflight`) and read `docs/input-quality.md`. Never force past errors;
never feed a multi-view sheet to a single-view backend; fix or flag matte
damage (eyes/ears/piping) instead of shipping it into a 27-minute run.
Golden cases in `golden/` are the regression memory — baselines are
promoted only by humans, never by the runner.

## Engineering notes (learned the expensive way)

- Blender headless drops unknown env vars in its subprocess Python: pass
  config via a temp file path after `--` and read `sys.argv[-1]`.
- Blender 5.2: `Vector.rotate` requires `Matrix.Rotation(...)`.
- glTF import convention: models face **+Y**; Pixal3D output needs
  `--facing 180` for our front camera. Declare such conventions in
  `capabilities().notes`, not in comments.
- Generation is slow by design (27 min on M5/16GB); never "fix" a timeout
  by faking completion.
- Keep `openfigura backends` truthful on a bare machine: missing binary is
  a reported state, not a crash.

## Workflow

Local test evidence belongs under the primary checkout's `.local/runs/<batch>/`,
including when code runs from a worktree. Keep the catalog at `.local/catalog.json`;
never scatter new result folders on Desktop. The whole `.local/` tree is gitignored.
Historical ledgers keep their original hashes and command paths; relocation mappings
live in the catalog. User-owned references and external runtimes stay separate.

```sh
source .venv/bin/activate          # python3.14, brew on this machine
pip install -e ".[dev]"
python -m pytest tests -q
openfigura backends                # must report honestly, pass or fail
```

Before pushing: tests green, PROGRESS updated if anything was verified,
`git log -1 --show-signature`-style DCO trailer present. Push only to
`main` of the owner's repo when asked; never force-push shared history.

## Scope discipline

This is a tool layer, not an agent. If a change starts looking like
"the framework should decide…", stop: the user's Codex/opencode decides.
OpenFigura's job is a stable `figura_*` contract and an auditable ledger.
