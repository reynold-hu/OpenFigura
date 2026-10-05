#!/usr/bin/env python3
"""Golden-case runner: generate -> inspect -> render -> compare vs baseline.

Never promotes anything to baseline; --emit-candidates writes candidates/
for a human to review. Exits non-zero on structural regressions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openfigura.core import engine  # noqa: E402
from openfigura.core.preflight import preflight  # noqa: E402
from openfigura.core.task import Task  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "golden" / "cases"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run_case(case_dir: Path, work_root: Path, emit: bool) -> dict:
    case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    report = {"case": case["name"], "steps": {}, "pass": True, "notes": []}
    task = Task.create(work_root, name=case["name"])
    digest = task.stage_input(case_dir / "input.png")
    report["steps"]["input_sha256"] = digest
    if case.get("expect_input_sha256"):
        ok = digest == case["expect_input_sha256"]
        report["steps"]["input_match"] = ok
        report["pass"] &= ok

    check = preflight(case_dir / "input.png")
    report["steps"]["preflight"] = {"ok": check["ok"], "warnings": check["warnings"],
                                    "expected_warnings": case.get("expect_preflight_warnings", [])}
    report["pass"] &= check["ok"]
    if not check["ok"]:
        return report

    gen = engine.generate(task, case["backend"], case.get("params", {}))
    report["steps"]["generate"] = {"exit": gen["exit_code"], "wall_s": gen["wall_seconds"],
                                   "glb_sha256": gen.get("output_sha256")}
    report["pass"] &= gen["exit_code"] == 0
    if gen["exit_code"] != 0:
        return report

    insp = engine.inspect(task)
    expect = case.get("expect", {})
    report["steps"]["inspect"] = {"ok": insp["ok"], "triangles": insp["triangles"],
                                  "materials_with_pbr": insp["materials_with_pbr"]}
    report["pass"] &= insp["ok"] and insp["triangles"] >= expect.get("min_triangles", 1)

    ren = engine.render(task, samples=case.get("render_samples", 16),
                        facing_deg=case.get("facing_deg", 0))
    report["steps"]["render"] = {"status": ren["status"], "frames": ren["frames"]}
    report["pass"] &= ren["status"] == "pass"

    baseline = case_dir / "baseline"
    cand = case_dir / "candidates" if emit else None
    if cand and cand.exists():
        shutil.rmtree(cand)
    if cand:
        cand.mkdir(parents=True)
    for frame in sorted((task.root / "render").glob("*.png")):
        base = baseline / frame.name
        if not base.exists():
            report["notes"].append(f"no baseline for {frame.name} (first run? needs human approval)")
            continue
        same = sha(frame) == sha(base)
        report["steps"].setdefault("frames", {})[frame.name] = "match" if same else "differs"
        if case.get("strict_hash") and not same:
            report["pass"] = False
        if cand and not same:
            shutil.copy2(frame, cand / frame.name)
    if cand and task.root.exists():
        shutil.copy2(task.root / "provenance.json", cand / "provenance.json")
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default=None)
    ap.add_argument("--emit-candidates", action="store_true")
    ap.add_argument("--work", default="/tmp/openfigura-golden")
    args = ap.parse_args()
    cases = [p for p in sorted(ROOT.glob("*/case.json"))] if not args.case \
        else [ROOT / args.case / "case.json"]
    if not cases:
        print("no golden cases yet; add golden/cases/<name>/case.json", file=sys.stderr)
        return 2
    failures = 0
    for cf in cases:
        rep = run_case(cf.parent, Path(args.work), args.emit_candidates)
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        failures += 0 if rep["pass"] else 1
    print(f"GOLDEN: {len(cases)} cases, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
