# Testing guide / 测试指南

How to evaluate OpenFigura on **your** machine, and how to build your own
test set. Bilingual: 中文见每节第二段。

## 1. First: can your machine run it? / 先测环境

```sh
openfigura syscheck        # or MCP tool figura_syscheck
```

Reads OS/arch/RAM/disk/GPU (best-effort), probes every registered backend,
and returns a tiered verdict:

| verdict | meaning | action |
|---|---|---|
| `ready` | all floors met, backends found | go |
| `capable` | works but tight (e.g. 8–16 GB RAM, <30 GB disk) | lower `res`, expect longer runs |
| `blocked` | hard floor missed | fix what `problems[]` names verbatim |

Floors (source: verified hosts, not vibes): memory 8 GB hard / 16 GB
recommended; disk 12 GB hard / 30 GB recommended (weights ≈8 GB + task
history). GPU detection is best-effort — `none detected` means we cannot
see it, not that it is absent.

你的电脑能不能跑，一条命令出结论：`openfigura syscheck`（或 MCP 的
`figura_syscheck`）。它会检查系统、内存、磁盘、显卡（尽力而为）和每个后端是否就绪，
给出 ready / capable / blocked 三档判决和每条问题的原文。底线：内存 8GB 起（推荐 16GB），
磁盘 12GB 起（推荐 30GB，权重约 8GB）。

## 2. Run the shipped golden suite / 跑官方测试集

`golden/cases/` ships 8 graded inputs + 3 gate fixtures (see
`golden/README.md` for the roster and axes).

```sh
# gate fixtures only — seconds, safe anywhere:
python scripts/run_golden.py --case broken-tiny
python scripts/run_golden.py --case broken-sheet
python scripts/run_golden.py --case broken-jpeg

# full suite — REAL GENERATION, budget ~27 min/case on M5/16GB:
python scripts/run_golden.py --emit-candidates
```

`--emit-candidates` writes `candidates/` for human review; it never
touches `baseline/`. Baselines are promoted only by humans editing
case.json with `approved_by` (see golden/README rules).

门禁夹具（三张坏图）几秒钟就能跑完，任何机器都该先跑这个确认闸门在咬人。
完整套件会真实调用生成后端，一张图在 M5/16GB 上约 27 分钟，请量力而行。
`--emit-candidates` 只写候选目录给人看，永远不覆盖基线——基线只能由人类批准。

## 3. Evaluation criteria / 评估标准

Record per case, per machine. These are the axes that matter, in order:

1. **Gate correctness 门禁正确性** — broken fixtures must FAIL/WARN as
   declared. Any "pass" on a broken input is a regression, period.
2. **Structural integrity 结构完整性** — `figura_inspect` / `openfigura
   inspect`: `ok:true`, normals+UV present, PBR materials referenced,
   triangles within the case's expected band.
3. **Speed 生成速度** — `wall_seconds` from the ledger, reported WITH
   hardware class (`syscheck` output), backend and `res`. There is no
   absolute "fast": publish triples like
   `27m15s · Apple M5 16GB Metal · pixal3d q8 · res1024 · 8579 tokens`.
   Expect roughly: RTX 4070-class CUDA ≈ 3–8× faster than M5 at res 1024
   (unverified — measure and report; do not copy this number).
   速度永远和硬件档位、后端、分辨率绑定汇报，禁止裸报"多少分钟"。
4. **Reference fidelity 还原度** — human review of neutral renders vs
   input: eyes/face, silhouette, clothing detail, accessory placement.
   Agents may describe; only humans set `visual_approval`.
5. **Reproducibility 可复现性** — same seed + same host + same backend
   build → byte-identical GLB sha256 across two runs. Cross-machine
   parity is NOT guaranteed; that is why `strict_hash` is per-host.

## 4. Build your own test set / 自建测试集

1. Generate inputs with the prompts in `golden/prompts.md` (maintainer
   fixtures) or the master template in `docs/input-guide.md` (your own
   characters). 用 `golden/prompts.md` 的夹具提示词，或 `docs/input-guide.md`
   的万能母版自己造测试图。
2. For each image: `openfigura preflight my.png` — if it errors, fix the
   input first; the test measures the pipeline, not your reference art.
3. Create `golden/cases/<name>/` with `input.png` + `case.json` (copy an
   existing case and edit `axis`, `expect`, `facing_deg`).
4. Run your case: `python scripts/run_golden.py --case <name>`.
5. Want to share? PR the case (input + case.json + a paragraph of human
   review). Broken variants: derive them mechanically from one of your
   good cases — `golden/make_broken.py` shows the three standard
   degradations and why each exists.

## 5. Reporting results honestly / 汇报结果的规矩

- Always attach: `syscheck` verdict, backend + version, seed, res,
  wall_seconds, ledger path.
- Never report a cherry-picked seed as "the" result; state the seed and
  how many attempts you kept (each attempt is a ledger entry).
- Failures are welcome data: a case that consistently fails on 8 GB RAM
  is a documentation win, not something to hide by bumping floors.
