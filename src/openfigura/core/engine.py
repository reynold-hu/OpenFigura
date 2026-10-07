"""Engine: local asset operations shared by CLI and MCP frontends.

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
           facing_deg: int = 0, artifact: str = "model.glb", frame: int = 1) -> dict:
    if not isinstance(frame, int) or frame < 1:
        raise ValueError('frame must be a positive integer')
    glb = _model(task, artifact)
    if not glb.is_file():
        raise FileNotFoundError("run generate first")
    backend = registry.get("blender")
    caps = backend.capabilities()
    if not caps.available:
        raise RuntimeError(f"render backend unavailable: {caps.reason}")
    render_dir = task.root / "render" if artifact == "model.glb" else task.root / "render" / glb.stem
    if frame != 1:
        render_dir = render_dir / f"frame-{frame}"
    ledger = backend.render_views(glb, render_dir, views=views,
                                  samples=samples, facing_deg=facing_deg, frame=frame)
    ledger["status"] = "pass" if ledger["exit_code"] == 0 and ledger["frames"] else "fail"
    ledger["frame"] = frame
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


def rig(task: Task, calibration: Path, skin_method: str = 'automatic',
        artifact: str = 'model.glb') -> dict:
    """Experimental calibrated Rigify binding. Never silently fall back in skinning."""
    import math
    if skin_method not in {'automatic', 'capsule'}:
        raise ValueError('skin_method must be automatic or capsule')
    model = _model(task, artifact)
    if not model.is_file():
        raise FileNotFoundError(model)
    if inspect_glb(model)['has_skinning']:
        raise ValueError('model already has skinning; rebinding is not supported')
    output = task.artifact('model-rigged.glb')
    if output.exists() or output.with_suffix('.blend').exists():
        raise FileExistsError('rig candidate already exists; use a new task')
    data = json.loads(Path(calibration).read_text(encoding='utf-8'))
    if data.get('model_sha256') and data['model_sha256'] != sha256_file(model):
        raise ValueError('calibration was fitted to a different model')
    bones = data.get('bones')
    if not isinstance(bones, dict) or not bones:
        raise ValueError('calibration needs explicit bone coordinates')
    for name, bone in bones.items():
        for end in ('head', 'tail'):
            point = bone.get(end)
            if not isinstance(point, list) or len(point) != 3 or not all(isinstance(x, (int,float)) and math.isfinite(x) for x in point):
                raise ValueError(f'nonfinite or invalid bone {name}/{end}')
        if sum((a-b)**2 for a,b in zip(bone['head'], bone['tail'])) < 1e-12:
            raise ValueError(f'zero-length bone {name}')
    if 'head_rigid_min_z' in data and not (isinstance(data['head_rigid_min_z'], (int,float)) and math.isfinite(data['head_rigid_min_z'])):
        raise ValueError('head_rigid_min_z must be finite')
    clip = data.get('clip')
    if clip:
        if 'contact_checks' not in data:
            raise ValueError('animated rig requires explicit contact_checks regions')
        if not isinstance(clip.get('frames'), int) or not 1 <= clip['frames'] <= 10000:
            raise ValueError('clip frames must be an integer in 1..10000')
        if not isinstance(clip.get('fps',24), int) or not 1 <= clip.get('fps',24) <= 240:
            raise ValueError('clip fps must be in 1..240')
        for control, keys in clip.get('keyframes', {}).items():
            for frame, rotation in keys:
                if not isinstance(frame,int) or not 1 <= frame <= clip['frames'] or len(rotation)!=3 or not all(math.isfinite(x) for x in rotation):
                    raise ValueError(f'invalid keyframe for {control}')
    if 'contact_checks' in data:
        from openfigura.backends.contact import validate_config
        validate_config(data['contact_checks'])
    backend = registry.get('rigify')
    caps = backend.capabilities()
    if not caps.available:
        raise RuntimeError('Rigify unavailable: '+caps.reason)
    staged = task.root / 'input' / 'rig-calibration.json'
    if staged.exists():
        raise FileExistsError('calibration evidence already exists; use a new task')
    shutil.copy2(calibration, staged)
    evidence = {'backend':'rigify','source_artifact':artifact,'input_sha256':sha256_file(model),
                'calibration_sha256':sha256_file(staged),'skin_method':skin_method,
                'artifact':str(output.relative_to(task.root))}
    try:
        result = backend.rig(model, staged, output, skin_method)
        evidence.update(result)
        if not result.get('produced') or not output.is_file():
            raise RuntimeError('rigging failed; see ledger: '+result.get('stderr_tail',''))
        if 'contact_checks' in data and result.get('contact_validation',{}).get('status') != 'pass':
            raise RuntimeError('requested contact validation did not pass')
        report = inspect_glb(output)
        if not report['ok'] or not report['has_skinning']:
            raise RuntimeError('rigging output failed structural/skin inspection: '+str(report['problems']))
        evidence.update(status='pass',output_sha256=sha256_file(output),
                        joint_count=report['joint_count'],animation_clips=report['animation_clips'])
    except Exception as exc:
        evidence.update(status='fail',error=str(exc))
        task.record('rig', evidence)
        raise
    task.record('rig', evidence)
    return evidence
