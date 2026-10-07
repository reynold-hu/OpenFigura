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
    params = params or {}
    gen_input = task.root / "input" / image.name
    prepare = getattr(backend, "prepare_input", None)
    if callable(prepare):
        prep = prepare(gen_input, task.artifact("matte.glb"), params)
        if prep is not None:
            prep["input_sha256"] = sha256_file(gen_input)
            prep["status"] = "pass" if prep.get("produced") else "fail"
            if prep.get("produced"):
                prep["output_sha256"] = sha256_file(Path(prep["output"]))
            task.record("preprocess", prep)
            if not prep.get("produced"):
                raise RuntimeError(f"{backend_id} preprocessing exited "
                                   f"{prep.get('exit_code')}; see ledger")
            gen_input = Path(prep["output"])
    out = task.artifact("model.glb")
    ledger = backend.generate(gen_input, out, params)
    if not ledger.get("produced"):
        task.record("generate", {**ledger, "status": "fail"})
        raise RuntimeError(f"{backend_id} exited {ledger['exit_code']}; see ledger")
    ledger["input_sha256"] = sha256_file(gen_input)
    ledger["output_sha256"] = sha256_file(out)
    intermediate_files = [out.with_suffix(".ply"), out.with_name(out.stem + "_base.png")]
    view_dir = out.with_suffix(".svviews")
    if view_dir.is_dir():
        intermediate_files.extend(p for p in view_dir.rglob("*") if p.is_file())
    ledger["intermediate_hashes"] = {
        str(p.relative_to(task.root / "artifacts")): sha256_file(p)
        for p in intermediate_files if p.is_file()}
    ledger["status"] = "pass"
    task.record("generate", ledger)
    return ledger


def _model(task: Task, artifact: str) -> Path:
    if Path(artifact).name != artifact or "\\" in artifact or not artifact.endswith(".glb"):
        raise ValueError("artifact must be a GLB filename inside artifacts")
    return task.artifact(artifact)


def render(task: Task, views: list[str] | None = None, samples: int = 32,
           facing_deg: int = 0, artifact: str = "model.glb") -> dict:
    glb = _model(task, artifact)
    if not glb.is_file():
        raise FileNotFoundError("run generate first")
    backend = registry.get("blender")
    caps = backend.capabilities()
    if not caps.available:
        raise RuntimeError(f"render backend unavailable: {caps.reason}")
    render_dir = task.root / "render" if artifact == "model.glb" else task.root / "render" / glb.stem
    ledger = backend.render_views(glb, render_dir, views=views,
                                  samples=samples, facing_deg=facing_deg)
    ledger["status"] = "pass" if ledger["exit_code"] == 0 and ledger["frames"] else "fail"
    task.record("render", ledger)
    return ledger


def inspect(task: Task, artifact: str = "model.glb") -> dict:
    glb = _model(task, artifact)
    if not glb.is_file():
        raise FileNotFoundError("nothing to inspect; run generate first")
    report = inspect_glb(glb)
    report["sha256"] = sha256_file(glb)
    (task.root / ("inspect.json" if artifact == "model.glb" else glb.stem + "-inspect.json")).write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    task.record("inspect", {"ok": report["ok"], "meshes": report["meshes"],
                            "triangles": report["triangles"], "problems": report["problems"]})
    return report


def export(task: Task, dest: Path, fmt: str = "glb", artifact: str = "model.glb") -> dict:
    if fmt != "glb":
        raise ValueError(f"format {fmt!r} not supported yet; only 'glb'")
    glb = _model(task, artifact)
    report_path = task.root / ("inspect.json" if artifact == "model.glb" else glb.stem + "-inspect.json")
    if not glb.is_file():
        raise FileNotFoundError("nothing to export; run generate first")
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if not report.get("ok"):
            raise RuntimeError("refusing to export: inspection reported problems: "
                               + "; ".join(report["problems"]))
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    output_name = f"{task.id}.glb" if artifact == "model.glb" else f"{task.id}-{glb.stem}.glb"
    shutil.copy2(glb, dest / output_name)
    if report_path.is_file():
        shutil.copy2(report_path, dest / "inspect.json")
    shutil.copy2(task.root / "provenance.json", dest / "provenance.json")
    render_dir = task.root / "render" if artifact == "model.glb" else task.root / "render" / glb.stem
    for frame in sorted(render_dir.glob("*.png")):
        shutil.copy2(frame, dest / frame.name)
    manifest = {"task_id": task.id, "artifact": artifact, "files": sorted(p.name for p in dest.iterdir()),
                "glb_sha256": sha256_file(dest / output_name)}
    (dest / "export-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    task.record("export", {"dest": str(dest), **manifest})
    return manifest


def refine_texture(task: Task, views_dir: Path, roi_mask: Path | None = None,
                   strength: float = 1.0) -> dict:
    """Preserve original; emit a source-projected, independently reviewable candidate."""
    import math
    if not isinstance(strength, (int, float)) or not math.isfinite(strength) or not 0 <= strength <= 1:
        raise ValueError('strength must be finite and between 0 and 1')
    model = task.artifact('model.glb')
    if not model.is_file():
        raise FileNotFoundError('run generate first')
    output = task.artifact('model-refined.glb')
    if output.exists():
        raise FileExistsError('candidate already exists; use a new task to preserve its evidence')
    source = Path(views_dir).resolve()
    metadata = source / 'transforms.json'
    meta = json.loads(metadata.read_text(encoding='utf-8'))
    if not meta.get('frames'):
        raise ValueError('reference camera set has no frames')
    files = {'transforms.json': metadata}
    for frame in meta['frames']:
        name = frame['file_path']
        path = (source / name).resolve()
        if Path(name).is_absolute() or not path.is_relative_to(source) or '..' in Path(name).parts:
            raise ValueError('reference image must stay inside its camera directory')
        if name == 'transforms.json' or not path.is_file():
            raise ValueError('reference image is missing or reserved')
        files[name] = path
    if roi_mask is not None and not Path(roi_mask).is_file():
        raise FileNotFoundError(roi_mask)
    backend = registry.get('photo-paint')
    caps = backend.capabilities()
    if not caps.available:
        raise RuntimeError('texture refinement unavailable: ' + caps.reason)
    staged = task.root / 'input' / 'texture-reference'
    if staged.exists():
        raise FileExistsError('reference evidence already exists; use a new task')
    staged.mkdir()
    hashes = {}
    for name, path in files.items():
        dest = staged / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        hashes[name] = sha256_file(dest)
    mask = None
    if roi_mask is not None:
        mask = task.root / 'input' / 'texture-roi-mask.png'
        shutil.copy2(roi_mask, mask)
        hashes['roi_mask'] = sha256_file(mask)
    evidence = {'backend': 'photo-paint', 'input_sha256': sha256_file(model),
                'views_dir': str(staged.relative_to(task.root)),
                'reference_hashes': hashes, 'strength': strength,
                'artifact': str(output.relative_to(task.root))}
    try:
        result = backend.refine(model, staged, output, mask=mask, strength=strength)
        evidence.update(result)
        if not result.get('produced') or not output.is_file():
            raise RuntimeError(f'texture refinement exited {result.get("exit_code")}: {result.get("stderr_tail", "")}')
        evidence.update(result, output_sha256=sha256_file(output), status='pass')
    except Exception as exc:
        evidence.update(status='fail', error=str(exc))
        task.record('refine_texture', evidence)
        raise
    task.record('refine_texture', evidence)
    return evidence
