"""Engine: local asset operations shared by CLI and MCP frontends.

    generate  reference image -> textured GLB via a registered backend
    render    GLB -> neutral multi-view frames
    inspect   GLB -> structural report (stdlib-only)
    export    collect verified artifacts into a delivery folder

Each verb appends to the task ledger; nothing is recorded that did not run.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from openfigura.core import registry
from openfigura.core.contracts import AssetRef
from openfigura.core.inspect import inspect_glb
from openfigura.core.preflight import preflight
from openfigura.core.task import Task, sha256_file
from openfigura.core.workflow import Workflow


def set_style(task: Task, spec: dict) -> dict:
    """Validate project-wide pixel parameters; preserve every revision."""
    from openfigura.core.style import StyleSpec
    validated = StyleSpec.from_dict(spec)
    task.record_style(validated)
    return {'status': 'pass', 'style_spec': validated.to_dict(),
            'visual_approval': 'pending'}


def project_style(task: Task) -> dict:
    from openfigura.core.style import StyleSpec
    for entry in reversed(task.entries):
        if entry['step'] == 'style':
            return {'status': 'pass',
                    'style_spec': StyleSpec.from_dict(entry['style_spec']).to_dict(),
                    'visual_approval': 'pending'}
    return {'status': 'unset', 'style_spec': None}


def workflow_submit(task: Task, request: dict) -> dict:
    """Persist a request; an execution worker is a separate future component."""
    from openfigura.core.contracts import AssetRef
    from openfigura.core.workflow import Workflow
    expected = {'step', 'inputs', 'params', 'backend', 'backend_version'}
    if not isinstance(request, dict) or set(request) != expected:
        raise ValueError('workflow request fields must match the schema exactly')
    if not isinstance(request['inputs'], list):
        raise ValueError('inputs must be a list of asset references')
    return Workflow(task.root).submit(
        request['step'], [AssetRef.from_dict(item) for item in request['inputs']],
        request['params'], request['backend'], request['backend_version'])


def workflow_status(task: Task, stage_id: str | None = None) -> dict:
    from openfigura.core.workflow import Workflow
    return Workflow(task.root).status(stage_id)


def workflow_cancel(task: Task, stage_id: str) -> dict:
    from openfigura.core.workflow import Workflow
    return Workflow(task.root).cancel(stage_id)


def workflow_resume(task: Task, stage_id: str) -> dict:
    from openfigura.core.workflow import Workflow
    return Workflow(task.root).resume(stage_id)


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
    dest = Path(dest)
    output_name = f"{task.id}.glb" if artifact == "model.glb" else f"{task.id}-{glb.stem}.glb"
    # Inspect and publish a private snapshot, so an active writer cannot switch
    # the source bytes between inspection and delivery.
    with tempfile.TemporaryDirectory(prefix='openfigura-export-') as staging:
        snapshot = Path(staging) / 'model.glb'
        shutil.copy2(glb, snapshot)
        current_hash = sha256_file(snapshot)
        try:
            current_report = inspect_glb(snapshot)
        except (ValueError, KeyError, IndexError) as exc:
            raise RuntimeError('refusing to export: current GLB cannot be inspected') from exc
        if not current_report['ok']:
            raise RuntimeError('refusing to export: current asset failed inspection: '
                               + '; '.join(current_report['problems']))
        if sha256_file(snapshot) != current_hash or sha256_file(glb) != current_hash:
            raise RuntimeError('refusing to export: asset changed during inspection')
        saved_report = None
        if report_path.is_file():
            saved_report = report_path.read_text(encoding='utf-8')
            report = json.loads(saved_report)
            if report.get('sha256') and report['sha256'] != current_hash:
                raise RuntimeError('refusing to export: asset changed since inspection; inspect again')
            if not report.get('ok'):
                raise RuntimeError('refusing to export: inspection reported problems: '
                                   + '; '.join(report['problems']))
        dest.mkdir(parents=True, exist_ok=True)
        temporary_output = None
        try:
            with tempfile.NamedTemporaryFile(dir=dest, suffix='.export-tmp', delete=False) as handle:
                temporary_output = Path(handle.name)
            shutil.copy2(snapshot, temporary_output)
            if sha256_file(temporary_output) != current_hash:
                raise RuntimeError('refusing to export: copied bytes failed hash verification')
            os.replace(temporary_output, dest / output_name)
        finally:
            if temporary_output is not None and temporary_output.exists():
                temporary_output.unlink()
    if saved_report is not None:
        (dest / 'inspect.json').write_text(saved_report, encoding='utf-8')
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


def _quarantine_candidate(task: Task, output: Path) -> list[str]:
    """Preserve rejected tool-owned files outside normal deliverable paths."""
    files = [p for p in (output, output.with_suffix('.blend')) if p.is_file()]
    if not files:
        return []
    folder = task.root / 'artifacts' / 'rejected' / uuid.uuid4().hex
    folder.mkdir(parents=True, exist_ok=False)
    rejected = []
    for path in files:
        dest = folder / path.name
        shutil.move(str(path), str(dest))
        rejected.append(str(dest.relative_to(task.root)))
    return rejected


def autorig(task: Task, backend: str = 'mia', device: str = 'cpu', seed: int = 42,
            query_chunk: int = 8192, artifact: str = 'model.glb') -> dict:
    """External neural joint/weight prediction, independent of manual calibration."""
    if device not in {'cpu','cuda'}:
        raise ValueError('device must be cpu or cuda; MPS is not verified')
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError('seed must be an unsigned 32-bit integer')
    if type(query_chunk) is not int or not 1 <= query_chunk <= 65536:
        raise ValueError('query_chunk must be in 1..65536')
    model = _model(task, artifact)
    if not model.is_file():
        raise FileNotFoundError(model)
    if inspect_glb(model)['has_skinning']:
        raise ValueError('model already has skinning')
    output = task.artifact('model-autorig.glb')
    if output.exists() or output.with_suffix('.blend').exists():
        raise FileExistsError('autorig candidate already exists; use a fresh task')
    solver = registry.get(backend)
    caps = solver.capabilities()
    if not caps.available:
        raise RuntimeError('neural rig unavailable: '+caps.reason)
    evidence = {'backend':backend,'source_artifact':artifact,'input_sha256':sha256_file(model),
                'device':device,'seed':seed,'query_chunk':query_chunk,
                'artifact':str(output.relative_to(task.root)),'visual_approval':'pending'}
    try:
        result = solver.autorig(model,output,device=device,seed=seed,query_chunk=query_chunk)
        evidence.update(result)
        if not result.get('produced') or not output.is_file():
            raise RuntimeError('neural rig failed: '+result.get('stderr_tail','see artifact logs'))
        if result.get('fit_validation',{}).get('status') != 'pass':
            raise RuntimeError('neural skeleton continuity validation did not pass')
        if result.get('manual_coordinates') is not False:
            raise RuntimeError('neural rig result did not confirm automatic coordinates')
        report = inspect_glb(output)
        if not report['ok'] or not report['has_skinning']:
            raise RuntimeError('neural rig output failed skin/structural inspection')
        if sha256_file(model) != evidence['input_sha256']:
            raise RuntimeError('neural backend modified original model')
        evidence.update(status='pass',output_sha256=sha256_file(output),joint_count=report['joint_count'])
    except Exception as exc:
        evidence.update(status='fail',error=str(exc),rejected_artifacts=_quarantine_candidate(task,output))
        task.record('autorig',evidence)
        raise
    task.record('autorig',evidence)
    return evidence


def retarget(task: Task, animation: Path, artifact: str = 'model-autorig.glb',
             frames: int = 31, fps: int = 24) -> dict:
    """Native same-name humanoid retargeting with compulsory regional contact gate."""
    if type(frames) is not int or not 1 <= frames <= 240:
        raise ValueError('frames must be in 1..240')
    if type(fps) is not int or not 1 <= fps <= 120:
        raise ValueError('fps must be in 1..120')
    model=_model(task,artifact);animation=Path(animation)
    if not model.is_file() or not animation.is_file():raise FileNotFoundError('target or animation missing')
    if not inspect_glb(model)['has_skinning']:raise ValueError('target must have a skin')
    source_report=inspect_glb(animation)
    clip_problems=[p for p in source_report['problems'] if p not in {'missing NORMAL attribute','missing TEXCOORD attribute','primitives present but no PBR material'}]
    if clip_problems or not source_report['has_skinning'] or not source_report['animation_clips']:
        raise ValueError('animation must be a valid skinned GLB with clips')
    output=task.artifact('model-animated.glb')
    if output.exists() or output.with_suffix('.blend').exists():raise FileExistsError('animated candidate exists; use fresh task')
    staged=task.root/'input/animation-source.glb'
    if staged.exists():raise FileExistsError('animation evidence exists; use fresh task')
    solver=registry.get('native-motion');caps=solver.capabilities()
    if not caps.available:raise RuntimeError('native motion unavailable: '+caps.reason)
    shutil.copy2(animation,staged)
    evidence={'source_artifact':artifact,'input_sha256':sha256_file(model),
        'animation_sha256':sha256_file(staged),'frames':frames,'fps':fps,'visual_approval':'pending',
        'artifact':str(output.relative_to(task.root))}
    try:
        result=solver.retarget(model,staged,output,frames,fps);evidence.update(result)
        if not result.get('produced'):raise RuntimeError('retarget failed: '+result.get('stderr_tail','see logs'))
        if result.get('contact_validation',{}).get('status')!='pass':raise RuntimeError('contact validation failed')
        report=inspect_glb(output)
        if not report['ok'] or not report['has_skinning'] or not report['animation_clips']:
            raise RuntimeError('animated candidate failed inspection')
        if len(report['animation_clips'])!=1:raise RuntimeError('retarget must export only one checked clip')
        if sha256_file(model)!=evidence['input_sha256']:raise RuntimeError('retarget changed original target')
        evidence.update(status='pass',output_sha256=sha256_file(output),animation_clips=report['animation_clips'])
    except Exception as exc:
        evidence.update(status='fail',error=str(exc),rejected_artifacts=_quarantine_candidate(task,output))
        task.record('retarget',evidence)
        raise
    task.record('retarget',evidence);return evidence


def mesh(task: Task, operation: str, params: dict | None = None,
         artifact: str = 'model.glb') -> dict:
    """Static-mesh processing in an isolated Blender process (original tools).

    Deterministic candidate name '<artifact stem>-<operation>.glb' so the
    durable stage record, the ledger and the bytes always agree.
    """
    backend = registry.get('blender-mesh-tools')
    caps = backend.capabilities()
    if not caps.available:
        raise RuntimeError('mesh tools unavailable: ' + caps.reason)
    model = _model(task, artifact)
    if not model.is_file():
        raise FileNotFoundError('nothing to process; run generate first')
    out = task.artifact(f'{model.stem}-{operation}.glb')
    if out.exists() or out.with_suffix('.mesh-report.json').exists():
        raise FileExistsError('mesh candidate already exists; use a new task')
    evidence = {'backend': backend.id, 'source_artifact': artifact, 'operation': operation,
                'input_sha256': sha256_file(model), 'params': dict(params or {}),
                'artifact': str(out.relative_to(task.root)), 'visual_approval': 'pending'}
    try:
        result = backend.process(model, out, operation, params or {})
        evidence.update(result)
        if result['exit_code'] != 0 or not out.is_file():
            raise RuntimeError(f"mesh {operation} exited {result['exit_code']}: "
                               + (result.get('stderr_tail') or '')[-500:])
        if not result.get('report'):
            raise RuntimeError(f'mesh {operation} produced no machine-readable report')
        evidence.update(status='pass', output_sha256=sha256_file(out))
    except Exception as exc:
        evidence.update(status='fail', error=str(exc))
        task.record('mesh', evidence)
        raise
    task.record('mesh', evidence)
    return evidence


def _backend_version(backend_id: str) -> str:
    import openfigura
    fallback = 'openfigura-' + openfigura.__version__
    try:
        notes = registry.probe(backend_id).notes or {}
    except Exception:
        return fallback
    for key in ('version', 'binary_version'):
        value = notes.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return fallback


def _dict_param(params: dict, key: str) -> dict:
    value = params.get(key) or {}
    if not isinstance(value, dict):
        raise ValueError(f"params[{key!r}] must be an object")
    return dict(value)


def _stage_inputs(task: Task, refs: list[AssetRef], sandbox: Task) -> dict[str, Path]:
    staged: dict[str, Path] = {}
    for ref in refs:
        source = ref.verify(task.root)
        name = Path(ref.task_relative_path).name
        if name in staged:
            raise ValueError(f'input basenames must be unique; collision on {name!r}')
        dest = sandbox.artifact(name) if ref.kind == 'model' else sandbox.root / 'input' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        staged[name] = dest
    return staged


def _require_input(staged: dict[str, Path], params: dict, key: str) -> Path:
    name = params.get(key)
    if not isinstance(name, str) or name not in staged:
        raise ValueError(f'params[{key!r}] must name a declared input basename')
    return staged[name]


def _pair(sandbox: Task, rel: str, kind: str) -> tuple[str, str]:
    if not (sandbox.root / rel).is_file():
        raise RuntimeError(f'verb reported pass but output is missing: {rel}')
    return (rel, kind)


def _blend_pair(sandbox: Task, stem: str) -> list[tuple[str, str]]:
    return [_pair(sandbox, f'artifacts/{stem}.blend', 'blend')] \
        if (sandbox.artifact(f'{stem}.blend')).is_file() else []


def _run_inspect(sandbox, staged, params):
    return inspect(sandbox, artifact=params.get('artifact', 'model.glb'))


def _outputs_inspect(sandbox, params, result):
    artifact = params.get('artifact', 'model.glb')
    name = 'inspect.json' if artifact == 'model.glb' else f'{Path(artifact).stem}-inspect.json'
    return [_pair(sandbox, name, 'report')]


def _run_generate(sandbox, staged, params):
    backend = params.get('backend')
    if not isinstance(backend, str) or not backend.strip():
        raise ValueError("params['backend'] must be a backend id")
    return generate(sandbox, backend, _dict_param(params, 'params'),
                    force=bool(params.get('force', False)))


def _outputs_generate(sandbox, params, result):
    refs = [_pair(sandbox, 'artifacts/model.glb', 'model')]
    if (sandbox.root / 'artifacts/matte.glb').is_file():
        refs.append(_pair(sandbox, 'artifacts/matte.glb', 'model'))
    return refs


def _run_render(sandbox, staged, params):
    views = params.get('views')
    if views is not None and (not isinstance(views, list)
                              or any(not isinstance(v, str) for v in views)):
        raise ValueError('views must be a list of strings')
    return render(sandbox, views=views, samples=params.get('samples', 32),
                  facing_deg=params.get('facing_deg', 0),
                  artifact=params.get('artifact', 'model.glb'),
                  frame=params.get('frame', 1))


def _outputs_render(sandbox, params, result):
    frames = sorted(p for p in (sandbox.root / 'render').rglob('*.png') if p.is_file())
    if not frames:
        raise RuntimeError('render produced no frames')
    return [_pair(sandbox, str(p.relative_to(sandbox.root)), 'frame') for p in frames]


def _run_rig(sandbox, staged, params):
    calibration = _require_input(staged, params, 'calibration')
    return rig(sandbox, calibration, skin_method=params.get('skin_method', 'automatic'),
               artifact=params.get('artifact', 'model.glb'))


def _outputs_rig(sandbox, params, result):
    return [_pair(sandbox, 'artifacts/model-rigged.glb', 'model')] \
        + _blend_pair(sandbox, 'model-rigged')


def _run_autorig(sandbox, staged, params):
    return autorig(sandbox, backend=params.get('backend', 'mia'),
                   device=params.get('device', 'cpu'), seed=params.get('seed', 42),
                   query_chunk=params.get('query_chunk', 8192),
                   artifact=params.get('artifact', 'model.glb'))


def _outputs_autorig(sandbox, params, result):
    return [_pair(sandbox, 'artifacts/model-autorig.glb', 'model')] \
        + _blend_pair(sandbox, 'model-autorig')


def _run_retarget(sandbox, staged, params):
    animation = _require_input(staged, params, 'animation')
    return retarget(sandbox, animation, artifact=params.get('artifact', 'model-autorig.glb'),
                    frames=params.get('frames', 31), fps=params.get('fps', 24))


def _outputs_retarget(sandbox, params, result):
    return [_pair(sandbox, 'artifacts/model-animated.glb', 'model')] \
        + _blend_pair(sandbox, 'model-animated')


def _run_export(sandbox, staged, params):
    return export(sandbox, sandbox.root / 'delivery', fmt=params.get('fmt', 'glb'),
                  artifact=params.get('artifact', 'model.glb'))


def _outputs_export(sandbox, params, result):
    files = sorted(p for p in (sandbox.root / 'delivery').rglob('*') if p.is_file())
    if not files:
        raise RuntimeError('export produced no files')
    kind = {'.glb': 'model', '.json': 'report', '.png': 'frame'}
    return [_pair(sandbox, str(p.relative_to(sandbox.root)),
                  kind.get(p.suffix.lower(), 'file')) for p in files]


def _run_mesh(sandbox, staged, params):
    operation = params.get('operation')
    if not isinstance(operation, str) or not operation.strip():
        raise ValueError("params['operation'] is required")
    return mesh(sandbox, operation, _dict_param(params, 'params'),
                artifact=params.get('artifact', 'model.glb'))


def _outputs_mesh(sandbox, params, result):
    stem = f'{Path(params.get("artifact", "model.glb")).stem}-{params["operation"]}'
    return [_pair(sandbox, f'artifacts/{stem}.glb', 'model'),
            _pair(sandbox, f'artifacts/{stem}.mesh-report.json', 'report')]


def _backend_for(step: str, params: dict) -> str:
    if step in {'generate', 'autorig'}:
        value = params.get('backend')
        if not isinstance(value, str) or not value.strip():
            raise ValueError("params['backend'] must be a backend id")
        return value
    return {'rig': 'rigify', 'mesh': 'blender-mesh-tools', 'retarget': 'native-motion',
            'render': 'blender', 'export': 'export-snapshot',
            'inspect': 'stdlib-inspect'}[step]


_EXEC_STEPS = {
    'inspect': {'allowed': {'artifact'}, 'run': _run_inspect, 'outputs': _outputs_inspect},
    'generate': {'allowed': {'backend', 'params', 'force'}, 'run': _run_generate, 'outputs': _outputs_generate},
    'render': {'allowed': {'views', 'samples', 'facing_deg', 'artifact', 'frame'}, 'run': _run_render, 'outputs': _outputs_render},
    'rig': {'allowed': {'calibration', 'skin_method', 'artifact'}, 'run': _run_rig, 'outputs': _outputs_rig},
    'autorig': {'allowed': {'backend', 'device', 'seed', 'query_chunk', 'artifact'}, 'run': _run_autorig, 'outputs': _outputs_autorig},
    'retarget': {'allowed': {'animation', 'artifact', 'frames', 'fps'}, 'run': _run_retarget, 'outputs': _outputs_retarget},
    'export': {'allowed': {'fmt', 'artifact'}, 'run': _run_export, 'outputs': _outputs_export},
    'mesh': {'allowed': {'operation', 'params', 'artifact'}, 'run': _run_mesh, 'outputs': _outputs_mesh},
}


def execute(task: Task, step: str, inputs: list[dict], params: dict | None = None) -> dict:
    """Run one engine verb under a durable stage record with verified outputs.

    Inputs are task-local AssetRefs; each stage executes the verb inside a
    private sandbox (stages/<stage_id>/) so a stage only ever sees the
    declared inputs, and a pass always names the bytes it produced.
    """
    import time
    spec = _EXEC_STEPS.get(step)
    if spec is None:
        raise ValueError(f'step {step!r} is not executable; known: {sorted(_EXEC_STEPS)}')
    if not isinstance(inputs, list):
        raise ValueError('inputs must be a list of asset reference dicts')
    refs = [AssetRef.from_dict(item) for item in inputs]
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ValueError('params must be an object')
    unknown = sorted(set(params) - spec['allowed'])
    if unknown:
        raise ValueError(f'unsupported parameters for {step}: {unknown}')
    backend_id = _backend_for(step, params)
    workflow = Workflow(task.root)
    stage = workflow.submit(step, refs, params, backend_id, _backend_version(backend_id))
    identity = {'stage_id': stage['stage_id'], 'step': step, 'backend': stage['backend'],
                'backend_version': stage['backend_version'], 'cache_key': stage['cache_key']}
    if stage['status'] == 'pass':
        task.record('execute', {**identity, 'status': 'pass',
                                'cached_from': stage['cached_from'], 'outputs': stage['outputs']})
        return {'status': 'pass', **identity, 'cached_from': stage['cached_from'],
                'outputs': stage['outputs']}
    started = time.monotonic()
    workflow.claim(stage['stage_id'])
    sandbox = Task.create(task.root / 'stages', name=stage['stage_id'])
    sandbox.record('stage', {**identity, 'inputs': stage['inputs'], 'params': stage['params']})
    try:
        staged = _stage_inputs(task, refs, sandbox)
        result = spec['run'](sandbox, staged, params)
        pairs = spec['outputs'](sandbox, params, result)
        outputs = [AssetRef(f'stages/{sandbox.id}/{rel}', sha256_file(sandbox.root / rel),
                           kind, step) for rel, kind in pairs]
        workflow.complete(stage['stage_id'], outputs)
    except Exception as exc:
        reason = f'{type(exc).__name__}: {exc}'
        sandbox.record('stage_result', {'stage_id': stage['stage_id'], 'status': 'fail',
                                        'error': reason})
        workflow.fail(stage['stage_id'], reason)
        task.record('execute', {**identity, 'status': 'fail', 'error': reason,
                                'wall_seconds': round(time.monotonic() - started, 2)})
        raise ValueError(f'stage {step} failed: {reason}') from exc
    summary = {'status': 'pass', **identity, 'cached_from': None,
               'outputs': [ref.to_dict() for ref in outputs],
               'wall_seconds': round(time.monotonic() - started, 2),
               'result': {key: value for key, value in result.items()
                          if key in {'ok', 'sha256', 'frames', 'exit_code', 'operation',
                                     'output', 'report_path', 'joint_count', 'glb_sha256',
                                     'produced', 'output_sha256'}}}
    sandbox.record('stage_result', {'stage_id': stage['stage_id'], 'status': 'pass',
                                    'outputs': summary['outputs'],
                                    'wall_seconds': summary['wall_seconds']})
    task.record('execute', {**identity, 'status': 'pass', 'cached_from': None,
                            'outputs': summary['outputs'],
                            'wall_seconds': summary['wall_seconds']})
    return summary
