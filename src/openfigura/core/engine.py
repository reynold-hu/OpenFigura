"""Engine: the four stable verbs every frontend (CLI, MCP, future agent) shares.

    generate  reference image -> textured GLB via a registered backend
    render    GLB -> neutral multi-view frames
    inspect   GLB -> structural report (stdlib-only)
    export    collect verified artifacts into a delivery folder

Each verb appends to the task ledger; nothing is recorded that did not run.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from openfigura.core import registry
from openfigura.core.inspect import inspect_glb
from openfigura.core.preflight import preflight
from openfigura.core.task import Task, sha256_file


def generate(task: Task, backend_id: str, params: dict | None = None,
             force: bool = False) -> dict:
    inputs = list((task.root / "input").glob("*"))
    if not inputs:
        raise ValueError("no staged input; copy a reference image first")
    image = next((p for p in inputs if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}), None)
    if image is None:
        raise ValueError("input folder has no readable image")
    check = preflight(task.root / "input" / image.name)
    task.record("preflight", check)
    if not check["ok"] and not force:
        raise RuntimeError("input preflight failed: " + "; ".join(check["errors"])
                           + " (fix the input; force only with good reason)")
    backend = registry.get(backend_id)
    caps = backend.capabilities()
    if not caps.available:
        raise RuntimeError(f"backend {backend_id!r} unavailable: {caps.reason}")
    out = task.artifact("model.glb")
    ledger = backend.generate(task.root / "input" / image.name, out, params or {})
    if not ledger.get("produced"):
        task.record("generate", {**ledger, "status": "fail"})
        raise RuntimeError(f"{backend_id} exited {ledger['exit_code']}; see ledger")
    ledger["output_sha256"] = sha256_file(out)
    ledger["status"] = "pass"
    task.record("generate", ledger)
    return ledger


def render(task: Task, views: list[str] | None = None, samples: int = 32,
           facing_deg: int = 0) -> dict:
    glb = task.artifact("model.glb")
    if not glb.is_file():
        raise FileNotFoundError("run generate first")
    backend = registry.get("blender")
    caps = backend.capabilities()
    if not caps.available:
        raise RuntimeError(f"render backend unavailable: {caps.reason}")
    ledger = backend.render_views(glb, task.root / "render", views=views,
                                  samples=samples, facing_deg=facing_deg)
    ledger["status"] = "pass" if ledger["exit_code"] == 0 and ledger["frames"] else "fail"
    task.record("render", ledger)
    return ledger


def inspect(task: Task) -> dict:
    glb = task.artifact("model.glb")
    if not glb.is_file():
        raise FileNotFoundError("nothing to inspect; run generate first")
    report = inspect_glb(glb)
    report["sha256"] = sha256_file(glb)
    (task.root / "inspect.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    task.record("inspect", {"ok": report["ok"], "meshes": report["meshes"],
                            "triangles": report["triangles"], "problems": report["problems"]})
    return report


def export(task: Task, dest: Path, fmt: str = "glb") -> dict:
    if fmt != "glb":
        raise ValueError(f"format {fmt!r} not supported yet; only 'glb'")
    glb = task.artifact("model.glb")
    report_path = task.root / "inspect.json"
    if not glb.is_file():
        raise FileNotFoundError("nothing to export; run generate first")
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if not report.get("ok"):
            raise RuntimeError("refusing to export: inspection reported problems: "
                               + "; ".join(report["problems"]))
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(glb, dest / f"{task.id}.glb")
    if report_path.is_file():
        shutil.copy2(report_path, dest / "inspect.json")
    shutil.copy2(task.root / "provenance.json", dest / "provenance.json")
    for frame in sorted((task.root / "render").glob("*.png")):
        shutil.copy2(frame, dest / frame.name)
    manifest = {"task_id": task.id, "files": sorted(p.name for p in dest.iterdir()),
                "glb_sha256": sha256_file(dest / f"{task.id}.glb")}
    (dest / "export-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    task.record("export", {"dest": str(dest), **manifest})
    return manifest
