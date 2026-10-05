# Golden cases

A golden case = one input image + fixed backend params + the artifacts the
maintainer accepted as baseline. They answer two questions on every change:

1. **Did quality regress?** (structural checks + render comparison)
2. **Does this input class still work?** (the input-quality contract,
   `docs/input-quality.md`, kept honest by real examples)

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
