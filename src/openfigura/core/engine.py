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
from openfigura.core.inspect import inspect_glb, gltf_document
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


SUPPORTED_FORMATS = ('glb', 'fbx', 'obj', 'stl', 'usd')


def skin_check(task: Task, config: dict, artifact: str = 'model.glb') -> dict:
    """Read-only weight diagnostics; completion is not skin-quality acceptance."""
    import copy
    import hashlib
    import time
    from openfigura.core.skin_quality import analyze_weights
    from openfigura.core.glb_skin import analyze_glb_weights
    if not isinstance(config, dict) or set(config)-{'families','pairs','mass_threshold','sum_tolerance','sample_limit'}:
        raise ValueError('unsupported skin-check configuration')
    config = copy.deepcopy(config)
    if 'families' not in config or 'pairs' not in config:
        raise ValueError('skin-check requires explicit families and pairs')
    options = {k:v for k,v in config.items() if k not in ('families','pairs')}
    analyze_weights([], config['families'], config['pairs'], **options)
    model = _model(task, artifact)
    output = task.artifact(model.stem+'-skin-check.json')
    if output.exists() or output.is_symlink():
        raise FileExistsError('skin-check report already exists; use a new task')
    expected = sha256_file(model); started = time.monotonic(); temporary = None; owned = None
    evidence = {'backend':'stdlib-skin-check','source_artifact':artifact,'input_sha256':expected,
                'config':config,'visual_approval':'pending'}
    try:
        with tempfile.TemporaryDirectory(prefix='openfigura-skin-input-') as folder:
            snapshot = Path(folder)/model.name
            shutil.copy2(model, snapshot)
            report = analyze_glb_weights(snapshot, config['families'], config['pairs'], **options)
            if sha256_file(snapshot) != expected or report.get('source_sha256') != expected:
                raise RuntimeError('skin-check input snapshot hash mismatch')
        if sha256_file(model) != expected:
            raise RuntimeError('skin-check source changed')
        if report.get('assessment') not in {'unavailable','invalid_weights','suspicious','no_flagged_conflicts'}:
            raise RuntimeError('skin-check report has invalid assessment')
        if report.get('skin_quality_accepted') is not False or report.get('collision_checked') is not False:
            raise RuntimeError('weight diagnostics cannot accept skin or collisions')
        report.update(status='pass', config=config, report_path=str(output.relative_to(task.root)),
                      backend='stdlib-skin-check', visual_approval='pending',
                      wall_seconds=time.monotonic()-started)
        payload=(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode()
        with tempfile.NamedTemporaryFile(dir=output.parent,suffix='.skin-tmp',delete=False) as handle:
            temporary=Path(handle.name);handle.write(payload);handle.flush()
            identity=os.fstat(handle.fileno());expected_owner=(identity.st_dev,identity.st_ino)
        os.link(temporary,output);owned=expected_owner
        actual=output.lstat()
        if (actual.st_dev,actual.st_ino)!=owned or sha256_file(output)!=hashlib.sha256(payload).hexdigest() or sha256_file(model)!=expected:
            raise RuntimeError('skin-check publication or source changed')
        evidence.update(status='pass',assessment=report['assessment'],report_path=report['report_path'],
                        output_sha256=hashlib.sha256(payload).hexdigest(),wall_seconds=time.monotonic()-started)
    except Exception as exc:
        if owned is not None and output.exists() and (output.lstat().st_dev,output.lstat().st_ino)==owned:
            output.unlink()
        evidence.update(status='fail',error=str(exc),wall_seconds=time.monotonic()-started)
        task.record('skin-check',evidence)
        raise
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
    task.record('skin-check',evidence)
    return report


def skin_probe(task: Task, config: dict, artifact: str = 'model.glb') -> dict:
    """Produce isolated deformation diagnostics, never an accepted motion asset."""
    import time
    from openfigura.backends.skin_probe import validate_config
    config=validate_config(config)
    backend=registry.get('blender-skin-probe');caps=backend.capabilities()
    if not caps.available:raise RuntimeError('skin probe unavailable: '+caps.reason)
    model=_model(task,artifact);expected=sha256_file(model);started=time.monotonic()
    output=task.root/'diagnostics'/('skin-probe-'+uuid.uuid4().hex)
    evidence={'backend':backend.id,'input_sha256':expected,'source_artifact':artifact,
              'config':config,'diagnostic_dir':str(output.relative_to(task.root)),
              'accepted_for_delivery':False,'visual_approval':'pending'}
    try:
        if output.parent.is_symlink() or not output.parent.resolve().is_relative_to(task.root.resolve()):
            raise ValueError('diagnostic parent must remain inside task without symlink')
        output.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='openfigura-probe-input-') as folder:
            snapshot=Path(folder)/model.name;shutil.copy2(model,snapshot)
            result=backend.probe(snapshot,output,config);evidence.update(result)
            if sha256_file(snapshot)!=expected:raise RuntimeError('probe input snapshot modified')
        if sha256_file(model)!=expected:raise RuntimeError('probe source changed')
        report=result.get('report') or {}
        if result.get('exit_code')!=0 or not result.get('produced') or report.get('status')!='complete':
            raise RuntimeError('skin probe did not complete diagnostics')
        if any(report.get(k) is not False for k in ['skin_quality_accepted','collision_checked','collision_accepted']):
            raise RuntimeError('skin probe cannot accept skin or collisions')
        if len(report.get('probes',[]))!=len(config['probes']):raise RuntimeError('missing probe results')
        wanted={'skin-probe-report.json','skin-probe.blend','rest-full.png'}
        for i in range(1,len(config['probes'])+1):wanted.update({f'probe-{i:03d}-full.png',f'probe-{i:03d}-closeup.png'})
        files=result.get('files')
        if not isinstance(files,list) or len(files)!=len(wanted) or set(files)!=wanted:
            raise RuntimeError('missing or unexpected diagnostic outputs')
        if output.is_symlink() or output.parent.is_symlink() or not output.resolve().is_relative_to(task.root.resolve()):
            raise RuntimeError('diagnostic directory replaced or escaped task')
        hashes={}
        for name in sorted(wanted):
            path=output/name
            if path.is_symlink() or not path.is_file():raise RuntimeError('invalid diagnostic output')
            hashes[str(path.relative_to(task.root))]=sha256_file(path)
        if json.loads((output/'skin-probe-report.json').read_text())!=report:
            raise RuntimeError('diagnostic report differs from worker result')
        json.dumps(report,allow_nan=False)
        evidence.update(status='pass',report=report,accepted_for_delivery=False,
                        input_sha256=expected,config=config,visual_approval='pending',
                        output_hashes=hashes,wall_seconds=time.monotonic()-started)
    except Exception as exc:
        # Retain partial diagnostics in their unique directory, never deliver them.
        evidence.update(status='fail',error=str(exc),accepted_for_delivery=False,
                        input_sha256=expected,config=config,visual_approval='pending',
                        wall_seconds=time.monotonic()-started)
        task.record('skin-probe',evidence);raise
    task.record('skin-probe',evidence)
    return evidence


def _deliver(dest: Path, name: str, source: Path, expect_sha: str | None = None) -> None:
    """Atomically place one file in dest via a same-directory temp, re-hashing bytes."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=dest, suffix='.export-tmp', delete=False) as handle:
            temporary = Path(handle.name)
        shutil.copy2(source, temporary)
        if expect_sha is not None and sha256_file(temporary) != expect_sha:
            raise RuntimeError(f'refusing to export: copied bytes failed hash verification ({name})')
        os.replace(temporary, dest / name)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def export(task: Task, dest: Path, fmt: str = "glb", artifact: str = "model.glb") -> dict:
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"format {fmt!r} unsupported; supported: {list(SUPPORTED_FORMATS)}")
    glb = _model(task, artifact)
    report_path = task.root / ("inspect.json" if artifact == "model.glb" else glb.stem + "-inspect.json")
    if not glb.is_file():
        raise FileNotFoundError("nothing to export; run generate first")
    dest = Path(dest)
    output_name = f"{task.id}.glb" if artifact == "model.glb" else f"{task.id}-{glb.stem}.glb"
    # Inspect and publish a private snapshot, so an active writer cannot switch
    # the source bytes between inspection and delivery.
    conversion = None
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
        if fmt != 'glb':
            backend = registry.get('blender-formats')
            caps = backend.capabilities()
            if not caps.available:
                raise RuntimeError('format export unavailable: ' + caps.reason)
            conversion_root = Path(staging)
            if fmt in {'obj','usd'}:
                conversion_root /= Path(output_name).stem + '-bundle'
                conversion_root.mkdir()
            converted = conversion_root / f'{Path(output_name).stem}.{backend.EXTENSIONS[fmt]}'
            conversion = backend.convert(snapshot, converted, fmt)
            if conversion['exit_code'] != 0 or not converted.is_file() or not conversion.get('report'):
                raise RuntimeError(f"format conversion {fmt} exited {conversion['exit_code']}: "
                                   + (conversion.get('stderr_tail') or '')[-400:])
        dest.mkdir(parents=True, exist_ok=True)
        _deliver(dest, output_name, snapshot, current_hash)
        if conversion is not None:
            ext = Path(conversion['output']).suffix.lstrip('.')
            primary = Path(conversion['output']).resolve().relative_to(Path(staging).resolve()).as_posix()
            target_primary = dest / primary
            target_primary.parent.mkdir(parents=True, exist_ok=True)
            _deliver(target_primary.parent, target_primary.name, Path(conversion['output']),
                     sha256_file(Path(conversion['output'])))
            _deliver(target_primary.parent, f'{Path(primary).stem}.{ext}-report.json', Path(conversion['report_path']))
            dependency_hashes = {}
            for item in conversion.get('sidecars', []):
                ref = AssetRef(item['relative_path'], item['sha256'], 'dependency', 'export')
                source = ref.verify(Path(conversion['output']).parent)
                relative = (Path(primary).parent / ref.task_relative_path).as_posix()
                target = (dest / relative).resolve()
                target.relative_to(dest.resolve())
                target.parent.mkdir(parents=True, exist_ok=True)
                _deliver(target.parent, target.name, source, ref.sha256)
                dependency_hashes[relative] = ref.sha256
            manifest_extra = {'primary': primary, 'converted_sha256': sha256_file(dest / primary),
                              'conversion_warnings': conversion['report'].get('warnings', []),
                              'dependency_sha256': dependency_hashes}
        else:
            manifest_extra = None
    if saved_report is not None:
        (dest / 'inspect.json').write_text(saved_report, encoding='utf-8')
    shutil.copy2(task.root / "provenance.json", dest / "provenance.json")
    render_dir = task.root / "render" if artifact == "model.glb" else task.root / "render" / glb.stem
    for frame in sorted(render_dir.glob("*.png")):
        shutil.copy2(frame, dest / frame.name)
    manifest = {"task_id": task.id, "artifact": artifact, "format": fmt,
                "files": sorted(p.relative_to(dest).as_posix() for p in dest.rglob('*') if p.is_file()),
                "glb_sha256": sha256_file(dest / output_name)}
    if manifest_extra:
        manifest.update(manifest_extra)
    (dest / "export-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    entry = {"dest": str(dest), **manifest}
    if conversion is not None:
        entry['conversion'] = {'command': conversion['command'], 'exit_code': conversion['exit_code'],
                               'wall_seconds': conversion['wall_seconds']}
    task.record("export", entry)
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


def _quarantine_files(task: Task, files: list[Path]) -> list[str]:
    """Move rejected tool-owned candidates out of deliverable paths, preserving them."""
    present = [p for p in files if p.is_file()]
    if not present:
        return []
    folder = task.root / 'artifacts' / 'rejected' / uuid.uuid4().hex
    folder.mkdir(parents=True, exist_ok=False)
    moved = []
    for path in present:
        dest = folder / path.name
        shutil.move(str(path), str(dest))
        moved.append(str(dest.relative_to(task.root)))
    return moved


def animate(task: Task, prompt: str, backend: str = 'unimate', repetitions: int = 3,
            cfg_scale: float = 3.0, seed: int = 42, artifact: str = 'model-autorig.glb',
            annotation: str | None = None, accept_nc_license: bool = False) -> dict:
    """Text-to-motion via an external generator; the contact gate decides pass.

    The backend never self-certifies: every generated clip is re-imported and
    run through the same regional contact evaluator the retarget gate uses.
    Only a gated clip is delivered, and licence acceptance is explicit per
    call because UniMate's released checkpoints are CC BY-NC 4.0.
    """
    import math
    if type(accept_nc_license) is not bool:
        raise ValueError('accept_nc_license must be a boolean, explicitly true to accept')
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError('prompt must be a nonempty string')
    if type(repetitions) is not int or not 1 <= repetitions <= 8:
        raise ValueError('repetitions must be an integer in 1..8')
    if isinstance(cfg_scale, bool) or not isinstance(cfg_scale, (int, float)) \
            or not math.isfinite(cfg_scale) or not 0 <= cfg_scale <= 12:
        raise ValueError('cfg_scale must be finite in 0..12')
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError('seed must be an unsigned 32-bit integer')
    if annotation is not None and not isinstance(annotation, str):
        raise ValueError('annotation must be a path string or null')
    model = _model(task, artifact)
    if not model.is_file():
        raise FileNotFoundError(model)
    report = inspect_glb(model)
    if not report['ok'] or not report['has_skinning']:
        raise ValueError('animate needs a valid skinned GLB; run autorig or rig first')
    solver = registry.get(backend)
    caps = solver.capabilities()
    if not caps.available:
        raise RuntimeError(f'backend {backend!r} unavailable: {caps.reason}')
    if backend == 'unimate' and not accept_nc_license:
        task.record('animate', {'status': 'blocked', 'backend': backend,
                                'reason': 'CC BY-NC 4.0 checkpoint licence not accepted'})
        raise RuntimeError('unimate released checkpoints are CC BY-NC 4.0 (non-commercial); '
                           'pass accept_nc_license=True explicitly to opt in — the acceptance '
                           'is recorded in the ledger')
    preflight = getattr(solver, 'preflight_rig', None)
    if callable(preflight):
        check = preflight(model)
        task.record('motion-preflight', check)
        if not check['ok']:
            raise RuntimeError('rig preflight failed: ' + '; '.join(check['problems']))
    out = task.artifact('model-motion.glb')
    if out.exists() or out.with_suffix('.blend').exists():
        raise FileExistsError('motion candidate exists; use a fresh task')
    workdir = task.root / 'motion' / f'{backend}-run'
    if workdir.exists():
        raise FileExistsError('motion work directory exists; use a fresh task')
    gate = registry.get('blender-motion-gate')
    evidence = {'backend': backend, 'source_artifact': artifact, 'input_sha256': sha256_file(model),
                'prompt': prompt, 'repetitions': repetitions, 'cfg_scale': cfg_scale, 'seed': seed,
                'weights_license_accepted': bool(accept_nc_license),
                'artifact': str(out.relative_to(task.root)), 'visual_approval': 'pending'}
    # External preprocessing receives a private copy, never the accepted source.
    snapshot = task.root / 'motion' / f'{backend}-input.glb'
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    if snapshot.exists():
        raise FileExistsError('motion input snapshot exists; use a fresh task')
    shutil.copy2(model, snapshot)
    annotation_path = Path(annotation).resolve() if annotation else None
    annotation_snapshot = None
    if annotation_path is not None:
        evidence['annotation_sha256'] = sha256_file(annotation_path)
        annotation_snapshot = snapshot.with_name(f'{backend}-annotation.json')
        if annotation_snapshot.exists():
            raise FileExistsError('motion annotation snapshot exists; use a fresh task')
        shutil.copy2(annotation_path, annotation_snapshot)
    try:
        motion = solver.generate_motion(snapshot, workdir, prompt, repetitions, cfg_scale, seed,
                                        str(annotation_snapshot) if annotation_snapshot else None)
        evidence['motion'] = {key: value for key, value in motion.items() if key != 'clips'}
        if motion.get('status') == 'awaiting_review':
            raise RuntimeError('backend stopped for joint-label/facing review ('
                               + str(motion.get('review', '')) + '); rerun with annotation=<file>')
        clips = [Path(p) for p in motion.get('clips') or []]
        if not motion.get('produced') or not clips:
            raise RuntimeError('motion backend produced no animated GLBs')
        if (sha256_file(model) != evidence['input_sha256']
                or sha256_file(snapshot) != evidence['input_sha256']):
            raise RuntimeError('motion backend modified its input model')
        if annotation_path and (sha256_file(annotation_path) != evidence['annotation_sha256']
                or sha256_file(annotation_snapshot) != evidence['annotation_sha256']):
            raise RuntimeError('motion backend modified annotation input')
        verdicts = []
        delivered = None
        for clip in clips:
            clip.resolve().relative_to(workdir.resolve())
            structural = inspect_glb(clip)
            if (not structural['ok'] or not structural['has_skinning']
                    or len(structural['animation_clips']) != 1
                    or structural['joint_count'] != report['joint_count']):
                raise RuntimeError('generated motion clip failed skin/animation inspection')
            gate_report = workdir / f'gate-{clip.stem}.json'
            result = gate.gate(clip, gate_report)
            status = (result.get('report') or {}).get('status', 'unavailable')
            verdicts.append({'clip': str(clip.relative_to(task.root)), 'status': status,
                             'exit_code': result['exit_code'],
                             'report': str(gate_report.relative_to(task.root))})
            if status == 'pass' and result['exit_code'] == 0 and delivered is None:
                delivered = clip
        evidence['gate'] = verdicts
        if delivered is None:
            rejected = _quarantine_files(task, clips)
            raise RuntimeError(f'no generated clip passed the contact gate; quarantined: {rejected}')
        if sha256_file(model) != evidence['input_sha256']:
            raise RuntimeError('motion source modified during contact checks')
        shutil.copy2(delivered, out)
        evidence.update(status='pass', output_sha256=sha256_file(out),
                        delivered_clip=str(delivered.relative_to(task.root)))
    except Exception as exc:
        evidence.update(status='fail', error=str(exc),
                        rejected_artifacts=_quarantine_candidate(task, out))
        task.record('animate', evidence)
        raise
    task.record('animate', evidence)
    return evidence


def transfer_rig(task: Task, source: str, artifact: str = 'model.glb',
                 params: dict | None = None) -> dict:
    """Copy skeleton and skin weights from a rigged GLB onto a matching static GLB.

    The transfer worker refuses non-overlap rest poses rather than guessing,
    and this verb refuses to deliver anything whose joint count diverges from
    the source or whose inputs were touched.
    """
    backend = registry.get('blender-rig-transfer')
    caps = backend.capabilities()
    if not caps.available:
        raise RuntimeError('rig transfer unavailable: ' + caps.reason)
    target = _model(task, artifact)
    src = _model(task, source)
    if target == src:
        raise ValueError('target and source artifacts must differ')
    if not target.is_file():
        raise FileNotFoundError(f'target artifact {artifact} missing')
    if not src.is_file():
        raise FileNotFoundError(f'source artifact {source} missing')
    target_report = inspect_glb(target)
    if not target_report['ok'] or target_report['has_skinning']:
        raise ValueError('target must be a clean static GLB without skinning')
    source_report = inspect_glb(src)
    if not source_report['has_skinning']:
        raise ValueError('source must carry a skeleton and skin weights')
    out = task.artifact(f'{target.stem}-transferred.glb')
    if out.exists() or out.with_suffix('.rig-transfer-report.json').exists():
        raise FileExistsError('transfer candidate exists; use a new task')
    evidence = {'backend': backend.id, 'target_artifact': artifact, 'source_artifact': source,
                'target_sha256': sha256_file(target), 'source_sha256': sha256_file(src),
                'params': dict(params or {}), 'artifact': str(out.relative_to(task.root)),
                'visual_approval': 'pending'}
    try:
        result = backend.transfer(target, src, out, params or {})
        evidence.update(result)
        if result['exit_code'] != 0 or not out.is_file():
            raise RuntimeError(f"rig transfer exited {result['exit_code']}: "
                               + (result.get('stderr_tail') or '')[-500:])
        if not result.get('report'):
            raise RuntimeError('rig transfer produced no machine-readable report')
        if result['report'].get('vertices_without_weights') != 0:
            raise RuntimeError('rig transfer has unweighted vertices or missing weight evidence')
        report = inspect_glb(out)
        if not report['ok'] or not report['has_skinning']:
            raise RuntimeError('transferred GLB failed structural/skin inspection: '
                               + str(report['problems']))
        if report['joint_count'] != source_report['joint_count']:
            raise RuntimeError(f"transferred joint count {report['joint_count']} does not "
                               f"match source {source_report['joint_count']}")
        if report['animation_clips']:
            raise RuntimeError('transfer must not fabricate animation clips')
        if sha256_file(target) != evidence['target_sha256'] or sha256_file(src) != evidence['source_sha256']:
            raise RuntimeError('transfer backend modified an input artifact')
        evidence.update(status='pass', output_sha256=sha256_file(out),
                        joint_count=report['joint_count'],
                        vertices_without_weights=result['report'].get('vertices_without_weights'))
    except Exception as exc:
        evidence.update(status='fail', error=str(exc),
                        rejected_artifacts=_quarantine_candidate(task, out))
        task.record('transfer_rig', evidence)
        raise
    task.record('transfer_rig', evidence)
    return evidence


def bake(task: Task, source: str, artifact: str, params: dict | None = None) -> dict:
    """High-to-low normal/AO bake; preserve both input assets."""
    high, low = _model(task, source), _model(task, artifact)
    if high == low:
        raise ValueError('bake requires distinct high and low assets')
    for path in (high, low):
        report = inspect_glb(path)
        allowed = {'primitives present but no PBR material', 'missing NORMAL attribute'}
        if path == high:
            allowed.add('missing TEXCOORD attribute')
        problems = [p for p in report['problems'] if p not in allowed]
        if problems or report['has_skinning'] or report['animation_clips']:
            raise ValueError('bake requires structurally valid static GLBs before rigging')
    backend = registry.get('blender-bake')
    caps = backend.capabilities()
    if not caps.available:
        raise RuntimeError('bake unavailable: ' + caps.reason)
    output = task.artifact('model-baked.glb')
    if output.exists() or output.with_suffix('.blend').exists():
        raise FileExistsError('bake candidate exists; use a new task')
    evidence = {'backend': backend.id, 'source_artifact': source, 'target_artifact': artifact,
                'high_sha256': sha256_file(high), 'low_sha256': sha256_file(low),
                'params': dict(params or {}), 'artifact': 'artifacts/model-baked.glb',
                'visual_approval': 'pending'}
    try:
        result = backend.bake(high, low, output, params or {})
        evidence.update(result)
        if result['exit_code'] != 0 or not result.get('produced'):
            raise RuntimeError('bake failed: ' + result.get('stderr_tail', 'see report'))
        report = result.get('report') or {}
        if report.get('uv_preserved') is not True or report.get('target_triangles') != report.get('result_triangles'):
            raise RuntimeError('bake changed target topology or UVs')
        if not inspect_glb(output)['ok']:
            raise RuntimeError('baked GLB failed structural inspection')
        for path in (Path(result['blend']), Path(result['report_path']),
                     *[Path(p) for p in result['textures'].values()]):
            path.resolve().relative_to(output.parent.resolve())
            if not path.is_file():
                raise RuntimeError('bake artifact missing: ' + path.name)
        if sha256_file(high) != evidence['high_sha256'] or sha256_file(low) != evidence['low_sha256']:
            raise RuntimeError('bake modified source assets')
        evidence.update(status='pass', output_sha256=sha256_file(output))
    except Exception as exc:
        evidence.update(status='fail', error=str(exc), rejected_artifacts=_quarantine_candidate(task, output))
        task.record('bake', evidence)
        raise
    task.record('bake', evidence)
    return evidence


def pivot(task: Task, mode: str = 'ground', artifact: str = 'model.glb') -> dict:
    """Rebase a static glTF asset to its ground or centre using root translation."""
    if mode not in ('ground', 'center'):
        raise ValueError('pivot mode must be ground or center')
    model = _model(task, artifact)
    if not model.is_file(): raise FileNotFoundError(model)
    backend = registry.get('gltf-pivot')
    caps = backend.capabilities()
    if not caps.available: raise RuntimeError('pivot unavailable: ' + caps.reason)
    out = task.artifact('model-pivot.glb')
    if out.exists() or out.with_suffix('.pivot-report.json').exists():
        raise FileExistsError('pivot candidate exists; use a fresh task')
    evidence = {'backend':'gltf-pivot','method':'static glTF root translation',
                'source_artifact':artifact,'input_sha256':sha256_file(model),
                'mode':mode,'artifact':'artifacts/model-pivot.glb','visual_approval':'pending'}
    owned = {}
    try:
        with tempfile.TemporaryDirectory(prefix='openfigura-pivot-input-') as folder:
            snapshot = Path(folder) / model.name; shutil.copy2(model, snapshot)
            result = backend.pivot(snapshot, out, mode); evidence.update(result)
            owned = result.get('owned_artifacts') or {}
            if sha256_file(snapshot) != evidence['input_sha256']:
                raise RuntimeError('pivot backend modified input snapshot')
        if result.get('exit_code') != 0 or not result.get('produced') or not out.is_file():
            raise RuntimeError('pivot produced no valid candidate')
        report = result.get('report') or {}
        if report.get('attribute_bytes_preserved') is not True or report.get('mode') != mode:
            raise RuntimeError('pivot lacks attribute-preservation evidence')
        report_path = Path(result['report_path'])
        report_path.resolve().relative_to(out.parent.resolve())
        if not report_path.is_file(): raise RuntimeError('pivot report missing')
        expected_hashes = {out: result.get('output_sha256'), report_path: result.get('report_sha256')}
        for path, digest in expected_hashes.items():
            info = path.lstat()
            if (path.is_symlink() or owned.get(str(path.absolute())) != [info.st_dev,info.st_ino]
                    or not isinstance(digest,str) or sha256_file(path) != digest):
                raise RuntimeError('pivot publication identity or hash changed')
        if report.get('output_sha256') != result.get('output_sha256') or json.loads(report_path.read_text()) != report:
            raise RuntimeError('pivot publication report mismatch')
        inspected = inspect_glb(out)
        allowed = {'missing NORMAL attribute','missing TEXCOORD attribute','primitives present but no PBR material'}
        if any(p not in allowed for p in inspected['problems']):
            raise RuntimeError('pivot candidate failed inspection')
        if sha256_file(model) != evidence['input_sha256']:
            raise RuntimeError('pivot source changed during processing')
        if sha256_file(out) != result['output_sha256'] or sha256_file(report_path) != result['report_sha256']:
            raise RuntimeError('pivot publication changed during validation')
        evidence.update(status='pass',output_sha256=result['output_sha256'])
    except Exception as exc:
        # Publication collisions belong to another writer. Quarantine only
        # identities explicitly returned by our successful publisher.
        candidates = []
        for path in (out, out.with_suffix('.pivot-report.json')):
            identity = owned.get(str(path.absolute()))
            try:
                info = path.lstat()
                if not path.is_symlink() and identity == [info.st_dev,info.st_ino]:
                    candidates.append(path)
            except FileNotFoundError:
                pass
        rejected = _quarantine_files(task,candidates) if candidates else []
        evidence.update(status='fail',error=str(exc),rejected_artifacts=rejected)
        task.record('pivot',evidence); raise
    task.record('pivot',evidence)
    return evidence


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
        # Backends only receive a private input snapshot. Hash checks detect
        # mutations without sacrificing the accepted source to preprocessing.
        with tempfile.TemporaryDirectory(prefix='openfigura-mesh-input-') as folder:
            snapshot = Path(folder) / model.name
            shutil.copy2(model, snapshot)
            result = backend.process(snapshot, out, operation, params or {})
            evidence.update(result)
            if sha256_file(snapshot) != evidence['input_sha256']:
                raise RuntimeError('mesh backend modified input snapshot')
        if result['exit_code'] != 0 or not out.is_file():
            raise RuntimeError(f"mesh {operation} exited {result['exit_code']}: "
                               + (result.get('stderr_tail') or '')[-500:])
        if not result.get('report'):
            raise RuntimeError(f'mesh {operation} produced no machine-readable report')
        if sha256_file(model) != evidence['input_sha256']:
            raise RuntimeError('mesh source changed during processing')
        evidence.update(status='pass', output_sha256=sha256_file(out))
    except Exception as exc:
        evidence.update(status='fail', error=str(exc),
                        rejected_artifacts=_quarantine_candidate(task, out))
        task.record('mesh', evidence)
        raise
    task.record('mesh', evidence)
    return evidence


def _first_input_image(task: Task, image: str | None) -> Path:
    if image is not None:
        candidate = Path(image)
        if candidate.is_absolute() or '\\' in image or '..' in candidate.parts:
            raise ValueError('image must be a task-relative path without ..')
        if candidate.name != image:
            folder = candidate.parts[0]
            if folder not in {'input', 'render'}:
                raise ValueError('image must live inside input/ or render/')
        return task.root / candidate
    candidates = [p for p in sorted((task.root / 'input').glob('*'))
                  if p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp'}
                  and not p.name.startswith('face-roi')]
    if not candidates:
        raise FileNotFoundError('no staged input image; stage a reference first')
    return candidates[0]


def face_landmarks(task: Task, image: str | None = None) -> dict:
    """478-point MediaPipe facial landmarks on a staged input; writes face-landmarks.json."""
    backend = registry.get('mediapipe-face')
    caps = backend.capabilities()
    if not caps.available:
        raise RuntimeError('face detection unavailable: ' + caps.reason)
    path = _first_input_image(task, image)
    if not path.is_file():
        raise FileNotFoundError(f'input image {path.name} missing')
    evidence = {'backend': backend.id, 'image': str(path.relative_to(task.root)),
                'image_sha256': sha256_file(path),
                'model_sha256': caps.notes.get('model_sha256'), 'visual_approval': 'pending'}
    try:
        detection = backend.detect(path)
        evidence['faces'] = detection['faces']
        if detection['faces'] == 0:
            evidence.update(status='no-face',
                            note='no face detected; stylized or profile input; not retried silently')
            task.record('face_landmarks', evidence)
            raise RuntimeError('no face detected; choose a clear frontal reference image')
        payload = {**evidence, 'points': detection['points'],
                   'landmarks': [[round(x, 6), round(y, 6), round(z, 6)]
                                 for x, y, z in detection['landmarks']],
                   'blendshapes': detection['blendshapes'], 'image_size': detection['image_size']}
        (task.root / 'face-landmarks.json').write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        evidence.update(status='pass', points=detection['points'],
                        artifact='face-landmarks.json')
    except Exception as exc:
        if evidence.get('status') is None:
            evidence.update(status='fail', error=str(exc))
            task.record('face_landmarks', evidence)
        raise
    task.record('face_landmarks', evidence)
    return evidence


def face_mask(task: Task, image: str | None = None, output: str = 'face-roi.png',
              expand: float = 0.06) -> dict:
    """Rasterise the facial oval from face-landmarks.json into an ROI mask PNG."""
    import math
    from openfigura.backends.face_align import polygon_from_landmarks, FACE_OVAL
    if isinstance(expand, bool) or not isinstance(expand, (int, float)) \
            or not math.isfinite(expand) or not 0 <= expand <= 1:
        raise ValueError('expand must be finite and in 0..1')
    if Path(output).name != output or '\\' in output or not output.endswith('.png'):
        raise ValueError('output must be a PNG filename inside input')
    record = task.root / 'face-landmarks.json'
    if not record.is_file():
        staged = task.root / 'input' / 'face-landmarks.json'
        if staged.is_file():
            record = staged
    if not record.is_file():
        raise FileNotFoundError('run face-landmarks first')
    data = json.loads(record.read_text(encoding='utf-8'))
    if image is not None and data.get('image') != str(Path(image)):
        raise ValueError('face-landmarks.json is for a different image')
    backend = registry.get('mediapipe-face')
    width, height = data['image_size']
    polygon = polygon_from_landmarks(data['landmarks'], width, height, FACE_OVAL, expand)
    out = task.root / 'input' / output
    if out.exists():
        raise FileExistsError('ROI mask exists; use a new output name')
    evidence = {'backend': backend.id, 'image': data['image'],
                'landmarks_sha256': sha256_file(record), 'expand': expand,
                'output': f'input/{output}', 'visual_approval': 'pending'}
    coverage = backend.draw_mask(polygon, width, height, out)
    evidence['coverage'] = round(coverage, 4)
    evidence['status'] = 'pass'
    task.record('face_mask', evidence)
    return evidence


def head_roi(task: Task, artifact: str = 'model.glb', views: str | None = None,
             output: str = 'head-roi.png', head_fraction: float = 0.18,
             expand: float = 0.08) -> dict:
    """Project the model's head band into its calibrated generation view and
    write the silhouette as an ROI mask for refine-texture. This is the
    stylized-character path where landmark detectors legitimately find no face."""
    backend = registry.get('photo-paint')
    caps = backend.capabilities()
    if not caps.available:
        raise RuntimeError('head ROI unavailable: ' + caps.reason)
    model = _model(task, artifact)
    if not model.is_file():
        raise FileNotFoundError(model)
    views_dir = model.with_suffix('.svviews') if views is None else Path(views)
    if not (views_dir / 'transforms.json').is_file():
        raise FileNotFoundError(f'no calibrated views beside {artifact}; run generate first')
    if Path(output).name != output or '\\' in output or not output.endswith('.png'):
        raise ValueError('output must be a PNG filename inside input')
    out = task.root / 'input' / output
    if out.exists():
        raise FileExistsError('head ROI mask exists; use a new output name')
    evidence = {'backend': backend.id, 'source_artifact': artifact, 'operation': 'head-roi-projection',
                'model_sha256': sha256_file(model),
                'views_dir': str(views_dir), 'head_fraction': head_fraction, 'expand': expand,
                'output': f'input/{output}', 'visual_approval': 'pending'}
    try:
        result = backend.head_roi(model, views_dir, out, head_fraction, expand)
        if not result.get('produced') or not out.is_file():
            raise RuntimeError('head ROI projection produced no mask')
        evidence.update(result, status='pass')
    except Exception as exc:
        evidence.update(status='fail', error=str(exc))
        task.record('head_roi', evidence)
        raise
    task.record('head_roi', evidence)
    return evidence


def face_expression_report(task: Task, image: str | None = None,
                           min_score: float = 0.3) -> dict:
    """Turn MediaPipe's 52 ARKit blendshape scores into a durable, readable report.

    Data comes from the same detection run as face-landmarks.json; this verb
    adds no model and no inference of its own.
    """
    import math
    if isinstance(min_score, bool) or not isinstance(min_score, (int, float)) \
            or not math.isfinite(min_score) or not 0 <= min_score <= 1:
        raise ValueError('min_score must be finite and in 0..1')
    record = task.root / 'face-landmarks.json'
    if not record.is_file():
        face_landmarks(task, image=image)
    data = json.loads(record.read_text(encoding='utf-8'))
    blendshapes = data.get('blendshapes') or {}
    if not blendshapes:
        raise RuntimeError('landmark record carries no blendshapes; nothing to report')
    ranked = sorted(blendshapes.items(), key=lambda kv: -kv[1])
    active = [(name, score) for name, score in ranked if score >= min_score]
    report = {'schema_version': 1, 'image': data.get('image'),
              'image_sha256': data.get('image_sha256'),
              'model_sha256': data.get('model_sha256'), 'threshold': min_score,
              'channels_total': len(ranked), 'channels_active': len(active),
              'active': [{'name': n, 'score': s} for n, s in active],
              'top5': [{'name': n, 'score': s} for n, s in ranked[:5]],
              'interpretation': 'ARKit-style expression weights from the reference photo; '
                                'not yet wired to any mesh morph target',
              'visual_approval': 'pending'}
    (task.root / 'face-expression-report.json').write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    evidence = {'backend': 'mediapipe-face', 'status': 'pass',
                'artifact': 'face-expression-report.json',
                'landmarks_sha256': sha256_file(record),
                'channels_active': len(active), 'top5': report['top5']}
    task.record('face_expression_report', evidence)
    return evidence


def expression_align(task: Task, artifact: str = 'model.glb', view: str = 'front') -> dict:
    """Register the CC0 hm08 face units onto a character via render landmarks.

    Requires face_landmarks on the rendered view (not the reference photo)
    and the camera manifest the render verb recorded. The acceptance gate is
    part of the verb: jawOpen's transferred field must concentrate on the
    character's head band, or the alignment is refused.
    """
    import numpy as np
    from openfigura._vendor import photo_paint as pp
    from openfigura.backends.makehuman_targets import (
        load_pack, PACK_SHA256, pack_path, base_mesh_path)
    from openfigura.backends.expression_field import (
        load_obj_positions, dense_deltas, nearest_map, sample_field)
    from openfigura.backends.expression_register import (
        BASE_ANCHOR_CHANNELS, anchor_from_target, landmarks_to_pixel, project_pixel,
        character_anchor, umeyama, gltf_to_blender_world)
    record_path = next((c for c in (task.root / 'face-landmarks.json',
                                    task.root / 'input' / 'face-landmarks.json') if c.is_file()), None)
    if record_path is None:
        raise FileNotFoundError('run face-landmarks on the rendered view first')
    record = json.loads(record_path.read_text(encoding='utf-8'))
    if not str(record.get('image', '')).endswith(f'/{view}.png') and record.get('image') != f'render/{view}.png':
        raise ValueError(f'face-landmarks.json was computed on {record.get("image")!r}, not the {view} render')
    model = _model(task, artifact)
    if not model.is_file():
        raise FileNotFoundError(model)
    render_dir = task.root / 'render' if artifact == 'model.glb' else task.root / 'render' / model.stem
    camera_file = next((c for c in [*(sorted(render_dir.rglob('camera.json')) if render_dir.is_dir() else []),
                                    task.root / 'input' / 'camera.json',
                                    task.root / 'camera.json'] if c.is_file()), None)
    if camera_file is None:
        raise FileNotFoundError('render carries no camera.json; re-render with the current build')
    camera = json.loads(camera_file.read_text(encoding='utf-8')).get(view)
    if not camera:
        raise ValueError(f'camera.json has no {view} entry')
    zip_path = pack_path('faceunits01')
    base_mesh = base_mesh_path()
    if not zip_path.is_file() or not base_mesh.is_file():
        raise FileNotFoundError('CC0 faceunits pack or hm08 base mesh missing; see third_party/makehuman-faceunits')
    targets = load_pack(zip_path, PACK_SHA256['faceunits01'])
    base_positions = load_obj_positions(base_mesh)
    positions, _, _, _ = pp.read_glb(model)
    world = gltf_to_blender_world(positions)
    pixels = landmarks_to_pixel([tuple(p) for p in record['landmarks']], record['image_size'])
    source, destination, names = [], [], []
    for name, channel in BASE_ANCHOR_CHANNELS.items():
        source.append(anchor_from_target(base_positions, targets[channel].indices))
        destination.append(character_anchor(project_pixel(*pixels[name], camera), world, camera))
        names.append(name)
    fit = umeyama(np.array(source).T, np.array(destination).T)
    aligned = fit['scale'] * (base_positions @ np.array(fit['rotation']).T) + np.array(fit['translation'])
    jaw = sample_field(dense_deltas(targets['jawOpen'], len(base_positions)),
                       nearest_map(aligned, world))
    magnitudes = np.linalg.norm(jaw, axis=1)
    moved = np.where(magnitudes > 1e-4)[0]
    up = int(np.argmax(world.max(axis=0) - world.min(axis=0)))
    span = float(np.ptp(world[:, up])) or 1.0
    height_fraction = float(((world[moved, up] - world[:, up].min()) / span).mean()) if len(moved) else 0.0
    acceptance = {'moved_vertices': int(len(moved)), 'mean_height_fraction': round(height_fraction, 3),
                  'threshold': 0.75}
    evidence = {'backend': 'blender-expressions', 'artifact': artifact, 'view': view,
                'model_sha256': sha256_file(model), 'landmarks_sha256': sha256_file(record_path),
                'camera_sha256': sha256_file(camera_file), 'pack_sha256': PACK_SHA256['faceunits01'],
                'anchors': names, 'fit': fit, 'acceptance': acceptance,
                'artifact_out': 'expression-alignment.json'}
    if not len(moved) or height_fraction < acceptance['threshold']:
        evidence.update(status='fail',
                        error=f'jawOpen field did not concentrate on the head band (mean height fraction {height_fraction:.2f})')
        task.record('expression_align', evidence)
        raise RuntimeError('expression alignment rejected by acceptance gate: '
                           + evidence['error'])
    (task.root / 'expression-alignment.json').write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    evidence.update(status='pass')
    task.record('expression_align', evidence)
    return evidence


def expressions(task: Task, artifact: str = 'model.glb', output: str = 'model-expressive.glb',
                min_score: float = 0.1, intensity: float = 1.0) -> dict:
    """Write ARKit-named morph targets onto the character from the registered
    CC0 face units, weighted by the reference expression scores."""
    import math
    import numpy as np
    from openfigura.backends.makehuman_targets import (
        load_pack, PACK_SHA256, pack_path, base_mesh_path)
    from openfigura.backends.expression_field import load_obj_positions
    from openfigura.backends.expression_register import build_payload
    if isinstance(min_score, bool) or not isinstance(min_score, (int, float)) \
            or not math.isfinite(min_score) or not 0 <= min_score <= 1:
        raise ValueError('min_score must be finite and in 0..1')
    if isinstance(intensity, bool) or not isinstance(intensity, (int, float)) \
            or not math.isfinite(intensity) or not 0 < intensity <= 2:
        raise ValueError('intensity must be finite and in (0, 2]')
    if Path(output).name != output or '\\' in output or not output.endswith('.glb'):
        raise ValueError('output must be a GLB filename inside artifacts')
    alignment_path = next((c for c in (task.root / 'expression-alignment.json',
                                       task.root / 'input' / 'expression-alignment.json') if c.is_file()), None)
    record_path = next((c for c in (task.root / 'face-landmarks.json',
                                    task.root / 'input' / 'face-landmarks.json') if c.is_file()), None)
    if alignment_path is None:
        raise FileNotFoundError('run expression_align first')
    if record_path is None:
        raise FileNotFoundError('run face-landmarks first')
    alignment = json.loads(alignment_path.read_text(encoding='utf-8'))
    model = _model(task, artifact)
    if not model.is_file():
        raise FileNotFoundError(model)
    if sha256_file(model) != alignment.get('model_sha256'):
        raise ValueError('alignment was computed for different model bytes; re-run expression_align')
    scores = {name: value for name, value in
              json.loads(record_path.read_text(encoding='utf-8')).get('blendshapes', {}).items()
              if name != '_neutral' and value >= min_score}
    if not scores:
        raise RuntimeError('no blendshape channel reaches min_score; nothing to transfer')
    if len(scores) > 12:
        scores = dict(sorted(scores.items(), key=lambda kv: -kv[1])[:12])
    targets = load_pack(pack_path('faceunits01'), PACK_SHA256['faceunits01'])
    missing = sorted(channel for channel in scores if channel not in targets)
    if missing:
        raise RuntimeError('channels without CC0 face units: ' + ', '.join(missing))
    channels = sorted(scores)
    base_positions = load_obj_positions(base_mesh_path())
    deltas = {channel: (targets[channel].indices, targets[channel].deltas) for channel in channels}
    payload = build_payload(base_positions, alignment['fit'], channels, deltas)
    payload['scores'] = np.array([round(float(scores[c]) * intensity, 4) for c in channels], dtype=np.float32)
    payload_path = task.root / 'expression-payload.npz'
    np.savez_compressed(payload_path, **payload)
    out = task.artifact(output)
    if out.exists() or out.with_suffix('.expressions-report.json').exists():
        raise FileExistsError('expressions candidate exists; use a new output name')
    backend = registry.get('blender-expressions')
    caps = backend.capabilities()
    if not caps.available:
        raise RuntimeError('expressions backend unavailable: ' + caps.reason)
    before = (sha256_file(model), sha256_file(alignment_path))
    evidence = {'backend': backend.id, 'source_artifact': artifact,
                'input_sha256': before[0], 'alignment_sha256': before[1],
                'channels': channels, 'weights': {c: round(float(scores[c]) * intensity, 4) for c in channels},
                'min_score': min_score, 'intensity': intensity,
                'artifact': str(out.relative_to(task.root)), 'visual_approval': 'pending'}
    try:
        result = backend.run(model, payload_path, out)
        evidence.update(result)
        if result['exit_code'] != 0 or not out.is_file():
            raise RuntimeError(f"expressions exited {result['exit_code']}: "
                               + (result.get('stderr_tail') or '')[-500:])
        document = gltf_document(out)
        primitives = document['meshes'][0]['primitives']
        morph_count = len(primitives[0].get('targets', []))
        names = (primitives[0].get('extras') or {}).get('targetNames') or \
            (document['meshes'][0].get('extras') or {}).get('targetNames') or []
        if morph_count != len(channels) or sorted(names) != channels:
            raise RuntimeError(f'morph verification failed: {morph_count} targets '
                               f'{names[:3]}… for {len(channels)} channels')
        if sha256_file(model) != before[0] or sha256_file(alignment_path) != before[1]:
            raise RuntimeError('expressions backend modified an input')
        evidence.update(status='pass', output_sha256=sha256_file(out),
                        morph_targets=morph_count, max_displacement=(result['report'] or {}).get(
                            'morph_targets', [{}])[0].get('max_displacement'))
    except Exception as exc:
        evidence.update(status='fail', error=str(exc))
        task.record('expressions', evidence)
        raise
    task.record('expressions', evidence)
    return evidence


def _backend_version(backend_id: str) -> str:
    import hashlib
    import inspect as python_inspect
    import openfigura
    fallback = 'openfigura-' + openfigura.__version__
    identity = {'package': fallback, 'backend': backend_id,
                'engine_sha256': sha256_file(Path(__file__))}
    # Composite verbs also depend on downstream validators/converters. A
    # generation adapter's unchanged code must not preserve an obsolete gate.
    composite = {'unimate': ['blender-motion-gate'],
                 'export-snapshot': ['blender-formats']}.get(backend_id, [])
    identity['downstream'] = {name: _backend_version(name) for name in composite}
    if backend_id in {'gltf-pivot','blender-skin-probe'}:
        identity['container_reader_sha256'] = sha256_file(Path(__file__).with_name('glb_faces.py'))
    if backend_id == 'stdlib-skin-check':
        identity['diagnostic_modules'] = {name:sha256_file(Path(__file__).with_name(name))
                                          for name in ['glb_faces.py','glb_skin.py','skin_quality.py']}
    try:
        backend = registry.get(backend_id)
        notes = backend.capabilities().notes or {}
        module = Path(python_inspect.getfile(type(backend)))
        identity['adapter_sha256'] = sha256_file(module)
        identity['class'] = type(backend).__qualname__
        # Worker code is part of the computation identity, not just the package label.
        dependencies = {'native-motion': ['motion_worker.py','retarget_worker.gd','contact.py'],
                        'mia': ['mia_worker.py','neural_bind_worker.py','neural_fit.py','mesh_sampling.py'],
                        'blender-motion-gate': ['motion_gate_worker.py','contact.py'],
                        'blender-rig-transfer': ['rig_transfer_worker.py'],
                        'blender-formats': ['format_export_worker.py'],
                        'blender-bake': ['bake_worker.py'],
                        'blender-mesh-tools': ['mesh_tools_worker.py'],
                        'blender-skin-probe':['skin_probe_worker.py']}.get(backend_id, [])
        identity['workers'] = {name: sha256_file(module.with_name(name))
                               for name in dependencies if module.with_name(name).is_file()}
        identity['declared_versions'] = {k: notes[k] for k in ('version','binary_version') if k in notes}
        binaries = {}
        for key in ('runtime','binary'):
            value = notes.get(key)
            if isinstance(value, str) and Path(value).is_file():
                binaries[key] = sha256_file(Path(value))
        identity['binaries'] = binaries
        models = notes.get('models')
        if isinstance(models, str) and Path(models).is_dir():
            identity['model_files'] = {p.name: [p.stat().st_size, p.stat().st_mtime_ns]
                                       for p in sorted(Path(models).glob('*.gguf'))}
    except Exception:
        # Builtin verbs have no external backend. Engine bytes still invalidate stale gates.
        pass
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()
    return fallback + '+' + digest


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


def _run_skin_check(sandbox, staged, params):
    artifact=params.get('artifact','model.glb')
    if artifact not in staged:
        raise ValueError('skin-check artifact must name a declared input basename')
    return skin_check(sandbox,params.get('config'),artifact)


def _outputs_skin_check(sandbox, params, result):
    import hashlib
    path=sandbox.root/result['report_path']
    expected=hashlib.sha256((json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode()).hexdigest()
    if path.is_symlink() or sha256_file(path)!=expected:
        raise RuntimeError('skin-check report changed before output declaration')
    return [_pair(sandbox,result['report_path'],'report')]


def _run_skin_probe(sandbox, staged, params):
    artifact=params.get('artifact','model.glb')
    if artifact not in staged:raise ValueError('skin-probe artifact must name a declared input basename')
    return skin_probe(sandbox,params.get('config'),artifact)


def _outputs_skin_probe(sandbox, params, result):
    outputs=[]
    for rel,expected in result['output_hashes'].items():
        path=sandbox.root/rel
        if path.is_symlink() or sha256_file(path)!=expected:raise RuntimeError('diagnostic output changed')
        kind='frame' if path.suffix=='.png' else 'blend' if path.suffix=='.blend' else 'report'
        outputs.append(_pair(sandbox,rel,kind))
    return outputs


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


def _run_animate(sandbox, staged, params):
    prompt = params.get('prompt')
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("params['prompt'] is required")
    return animate(sandbox, prompt, backend=params.get('backend', 'unimate'),
                   repetitions=params.get('repetitions', 3), cfg_scale=params.get('cfg_scale', 3.0),
                   seed=params.get('seed', 42), artifact=params.get('artifact', 'model-autorig.glb'),
                   annotation=str(_require_input(staged, params, 'annotation')) if params.get('annotation') else None,
                   accept_nc_license=params.get('accept_nc_license', False))


def _outputs_animate(sandbox, params, result):
    refs = [_pair(sandbox, 'artifacts/model-motion.glb', 'model')]
    refs += [(str(p.relative_to(sandbox.root)), 'report')
             for p in sorted((sandbox.root / 'motion').rglob('gate-*.json'))]
    return refs


def _run_transfer_rig(sandbox, staged, params):
    source = params.get('source')
    if not isinstance(source, str) or not source.strip():
        raise ValueError("params['source'] must name a rigged GLB artifact")
    return transfer_rig(sandbox, source, artifact=params.get('artifact', 'model.glb'),
                        params=dict(_dict_param(params, 'params')))


def _outputs_transfer_rig(sandbox, params, result):
    stem = f"{Path(params.get('artifact', 'model.glb')).stem}-transferred"
    return [_pair(sandbox, f'artifacts/{stem}.glb', 'model'),
            _pair(sandbox, f'artifacts/{stem}.rig-transfer-report.json', 'report')]


def _run_face_landmarks(sandbox, staged, params):
    return face_landmarks(sandbox, image=params.get('image'))


def _outputs_face_landmarks(sandbox, params, result):
    return [_pair(sandbox, 'face-landmarks.json', 'report')]


def _run_face_mask(sandbox, staged, params):
    return face_mask(sandbox, image=params.get('image'),
                     output=params.get('output', 'face-roi.png'),
                     expand=params.get('expand', 0.06))


def _outputs_face_mask(sandbox, params, result):
    return [_pair(sandbox, f"input/{params.get('output', 'face-roi.png')}", 'mask')]


def _run_head_roi(sandbox, staged, params):
    return head_roi(sandbox, artifact=params.get('artifact', 'model.glb'),
                    views=params.get('views'), output=params.get('output', 'head-roi.png'),
                    head_fraction=params.get('head_fraction', 0.18),
                    expand=params.get('expand', 0.08))


def _outputs_head_roi(sandbox, params, result):
    return [_pair(sandbox, f"input/{params.get('output', 'head-roi.png')}", 'mask')]


def _run_face_expression_report(sandbox, staged, params):
    return face_expression_report(sandbox, image=params.get('image'),
                                  min_score=params.get('min_score', 0.3))


def _outputs_face_expression_report(sandbox, params, result):
    return [_pair(sandbox, 'face-expression-report.json', 'report')]


def _run_expression_align(sandbox, staged, params):
    return expression_align(sandbox, artifact=params.get('artifact', 'model.glb'),
                            view=params.get('view', 'front'))


def _outputs_expression_align(sandbox, params, result):
    return [_pair(sandbox, 'expression-alignment.json', 'report')]


def _run_expressions(sandbox, staged, params):
    return expressions(sandbox, artifact=params.get('artifact', 'model.glb'),
                       output=params.get('output', 'model-expressive.glb'),
                       min_score=params.get('min_score', 0.1),
                       intensity=params.get('intensity', 1.0))


def _outputs_expressions(sandbox, params, result):
    stem = Path(params.get('output', 'model-expressive.glb')).stem
    return [_pair(sandbox, f"artifacts/{stem}.glb", 'model'),
            _pair(sandbox, f'artifacts/{stem}.expressions-report.json', 'report')]


def _backend_for(step: str, params: dict) -> str:
    if step in {'generate', 'autorig', 'animate'}:
        value = params.get('backend') if step != 'animate' else params.get('backend', 'unimate')
        if not isinstance(value, str) or not value.strip():
            raise ValueError("params['backend'] must be a backend id")
        return value
    return {'rig': 'rigify', 'mesh': 'blender-mesh-tools', 'retarget': 'native-motion',
            'render': 'blender', 'export': 'export-snapshot', 'transfer_rig': 'blender-rig-transfer',
            'inspect': 'stdlib-inspect', 'skin-check':'stdlib-skin-check', 'skin-probe':'blender-skin-probe', 'bake': 'blender-bake', 'pivot': 'gltf-pivot', 'face_landmarks': 'mediapipe-face', 'face_mask': 'mediapipe-face',
            'face_expression_report': 'mediapipe-face', 'head_roi': 'photo-paint',
            'expression_align': 'blender-expressions', 'expressions': 'blender-expressions'}[step]


def _run_pivot(sandbox, staged, params):
    return pivot(sandbox, params.get('mode','ground'), params.get('artifact','model.glb'))


def _outputs_pivot(sandbox, params, result):
    refs = [_pair(sandbox,'artifacts/model-pivot.glb','model'),
            _pair(sandbox,'artifacts/model-pivot.pivot-report.json','report')]
    for (relative, kind), key in zip(refs, ('output_sha256','report_sha256')):
        if sha256_file(sandbox.root / relative) != result[key]:
            raise RuntimeError('pivot publication changed before stage outputs')
    return refs


def _run_bake(sandbox, staged, params):
    return bake(sandbox, params['source'], params['artifact'], _dict_param(params, 'params'))


def _outputs_bake(sandbox, params, result):
    output = [_pair(sandbox, 'artifacts/model-baked.glb', 'model'),
              _pair(sandbox, 'artifacts/model-baked.blend', 'blend'),
              _pair(sandbox, 'artifacts/model-baked.bake-report.json', 'report')]
    output += [(str(Path(p).relative_to(sandbox.root)), 'texture') for p in result['textures'].values()]
    return output


_EXEC_STEPS = {
    'skin-probe': {'allowed': {'artifact','config'}, 'run': _run_skin_probe, 'outputs': _outputs_skin_probe},
    'skin-check': {'allowed': {'artifact','config'}, 'run': _run_skin_check, 'outputs': _outputs_skin_check},
    'pivot': {'allowed': {'mode','artifact'}, 'run': _run_pivot, 'outputs': _outputs_pivot},
    'bake': {'allowed': {'source', 'artifact', 'params'}, 'run': _run_bake, 'outputs': _outputs_bake},
    'inspect': {'allowed': {'artifact'}, 'run': _run_inspect, 'outputs': _outputs_inspect},
    'generate': {'allowed': {'backend', 'params', 'force'}, 'run': _run_generate, 'outputs': _outputs_generate},
    'render': {'allowed': {'views', 'samples', 'facing_deg', 'artifact', 'frame'}, 'run': _run_render, 'outputs': _outputs_render},
    'rig': {'allowed': {'calibration', 'skin_method', 'artifact'}, 'run': _run_rig, 'outputs': _outputs_rig},
    'autorig': {'allowed': {'backend', 'device', 'seed', 'query_chunk', 'artifact'}, 'run': _run_autorig, 'outputs': _outputs_autorig},
    'retarget': {'allowed': {'animation', 'artifact', 'frames', 'fps'}, 'run': _run_retarget, 'outputs': _outputs_retarget},
    'export': {'allowed': {'fmt', 'artifact'}, 'run': _run_export, 'outputs': _outputs_export},
    'mesh': {'allowed': {'operation', 'params', 'artifact'}, 'run': _run_mesh, 'outputs': _outputs_mesh},
    'animate': {'allowed': {'prompt', 'backend', 'repetitions', 'cfg_scale', 'seed', 'artifact',
                             'annotation', 'accept_nc_license'},
                'run': _run_animate, 'outputs': _outputs_animate},
    'transfer_rig': {'allowed': {'source', 'artifact', 'params'}, 'run': _run_transfer_rig,
                     'outputs': _outputs_transfer_rig},
    'face_landmarks': {'allowed': {'image'}, 'run': _run_face_landmarks, 'outputs': _outputs_face_landmarks},
    'face_mask': {'allowed': {'image', 'output', 'expand'}, 'run': _run_face_mask, 'outputs': _outputs_face_mask},
    'head_roi': {'allowed': {'artifact', 'views', 'output', 'head_fraction', 'expand'},
                 'run': _run_head_roi, 'outputs': _outputs_head_roi},
    'face_expression_report': {'allowed': {'image', 'min_score'},
                               'run': _run_face_expression_report,
                               'outputs': _outputs_face_expression_report},
    'expression_align': {'allowed': {'artifact', 'view'}, 'run': _run_expression_align,
                         'outputs': _outputs_expression_align},
    'expressions': {'allowed': {'artifact', 'output', 'min_score', 'intensity'},
                    'run': _run_expressions, 'outputs': _outputs_expressions},
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
    if step == 'animate':
        if type(params.get('accept_nc_license', False)) is not bool:
            raise ValueError('accept_nc_license must be a boolean')
        if params.get('annotation') is not None and params['annotation'] not in {
                Path(ref.task_relative_path).name for ref in refs}:
            raise ValueError('annotation must name a declared hash-verified input basename')
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
