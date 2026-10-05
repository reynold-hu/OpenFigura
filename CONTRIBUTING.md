# Contributing to OpenFigura

Thanks for being here. Small, honest contributions beat big claims.

## Ground rules

1. **AGPL stays.** Contributions are licensed AGPL-3.0-only. Use
   `git commit -s` (DCO sign-off — one line in your commit message stating
   you have the right to submit this work). No CLA; copyright stays with you.
2. **Evidence over assertions.** Every PR description that claims a result
   must include the command that produced it and where the output lives
   ("renders improved" is not evidence; `openfigura render … && diff` is).
   A capability that cannot run on the contributor's machine must report
   itself as unavailable, not fail obscurely or fake a pass.
3. **Never commit weights, runtimes, GLBs or task outputs.** They are
   fetched, not shipped (see `.gitignore`). Tests must run with fake
   backends and stdlib-only fixtures.
4. **Backend licenses are documented, not laundered.** Adding a backend
   means recording its license and hardware reality in `capabilities()` and
   the docs, exactly as it is.

## Dev setup

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests -q
```

Blender and generation runtimes are optional: `openfigura backends` probes
and reports honestly when they are missing.

## Where to start

- `docs/PROGRESS.md` lists verified vs. pending work — pending items with
  no owner are good first issues.
- New backends: implement the `Backend` protocol in
  `src/openfigura/backends/`, register it, add a fake-command test.
- New tools (CLI + MCP): add the verb to `core/engine.py` first, then wire
  both frontends. Never let CLI and MCP drift apart.

## Governance

Roadmap and design decisions live in `docs/` and issues, in the open.
Disagree in public; the maintainer arbitrates when consensus stalls.
Forks are welcome — see `TRADEMARK.md` for naming, and issues labeled
`upstream-wanted` if you'd rather your change live here.
