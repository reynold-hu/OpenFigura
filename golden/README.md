# Golden cases

A golden case = one input image + fixed backend params + the artifacts the
maintainer accepted as baseline. They answer two questions on every change:

1. **Did quality regress?** (structural checks + render comparison)
2. **Does this input class still work?** (the input-quality contract,
   `docs/input-quality.md`, kept honest by real examples)

## Current roster (committed 2026-10-05, user-generated via GPT Image)

| case | axis | status |
|---|---|---|
| `xiaoman-front` | front-view baseline (our character-sheet heroine) | awaiting first accepted run |
| `hoodie-side` | side profile; single-view inference | awaiting |
| `silver-scarf` | fine silver hair, earrings, scarf fringe; matte edges | awaiting |
| `dark-knight` | dark armor on light ground; silhouette; face hidden by helmet | awaiting |
| `tarot-box` | non-human prop; product three-quarter | awaiting |
| `scifi-stride` | complex game character; flowing hair + cape; stride pose (A-pose deviation on purpose) | awaiting |
| `crouch-pose` | crouched non-neutral pose + eyes covered by visor; worst-case inference | awaiting |
| `head-sculpt` | photoreal bust; facial-detail ceiling test; not full body | awaiting |
| `broken-tiny` | gate fixture: 256px from xiaoman-front → preflight ERROR | active |
| `broken-sheet` | gate fixture: 4× scifi-stride strip, aspect 3.09 → ERROR | active |
| `broken-jpeg` | gate fixture: 25% JPEG from silver-scarf → WARNING | active |

Broken fixtures are derived mechanically by `make_broken.py` (stdlib +
`sips` only; no AIGC for bad inputs — each degradation isolates exactly
one mechanism). Their case.json sets `expect_preflight`; the runner
passes them only when the gate bites.

Testing your own machine / building your own cases:
[`../docs/testing-guide.md`](../docs/testing-guide.md).

## Layout

```
cases/<name>/
  input.png        committed; the exact bytes that go into figura_new_task
  case.json        source, license, backend, params, expectations
  baseline/        accepted renders + inspect summary + provenance excerpt
```

## Rules

- **Inputs are committed; generated outputs are not** (except the small
  accepted baseline renders). A golden case without a baseline is a TODO,
  not a test.
- **Baselines are only updated by a human decision.** A runner may write
  `--emit-candidates`; promoting candidates to baseline requires editing
  case.json with `approved_by` and a date. Agents never self-approve.
- **Same-seed reproducibility is machine-dependent.** `strict_hash: true`
  baselines compare PNG hashes (same host, same backend build); otherwise
  comparison is structural + human eyeball on candidate frames. Record the
  host class in case.json.
- Every case declares its input-quality verdict: which preflight warnings
  fired and why they were acceptable.

## Running

```sh
python scripts/run_golden.py                 # all cases
python scripts/run_golden.py --case xiaoman-front
python scripts/run_golden.py --emit-candidates   # write candidates/, never touch baseline/
```

Cost honesty: one full Pixal3D generation is ~27 min on M5/16GB. The suite
is a release gate, not a per-commit test; per-commit runs `pytest tests`
with fake backends only.
