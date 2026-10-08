"""Optional external UniMate runtime: text-to-motion for arbitrary rigs.

Code here is OpenFigura (AGPL-3.0-only). UniMate's own code is MIT, but the
released checkpoints are CC BY-NC 4.0: every call must pass
accept_nc_license explicitly, and that acceptance lands in the ledger.
This adapter shells out to a user-provided checkout; nothing is vendored.
"""
from __future__ import annotations
import os
from pathlib import Path
from openfigura.backends import base
from openfigura.core import registry
from openfigura.core.inspect import gltf_document
from openfigura.core.registry import Capabilities

MODEL_MAX_JOINTS = 71  # UniMate pipeline limit (upstream rig_preprocess/pipeline.py)
WEIGHTS_LICENSE = 'CC BY-NC 4.0 (UniMate released checkpoints)'


def preflight_rig(path: Path) -> dict:
    """Offline UniMate ingest invariants, checked from the GLB JSON only.

    Derived from upstream behaviour: joint budget, single root bone, unique
    joint names (duplicates collapse into placeholder labels), skin present.
    """
    problems = []
    doc = gltf_document(Path(path))
    skins = doc.get('skins') or []
    nodes = doc.get('nodes') or []
    if not skins:
        return {'ok': False, 'problems': ['no skin: run autorig or rig first'],
                'joints': 0, 'duplicates': [], 'roots': 0}
    joints = skins[0].get('joints') or []
    names = [nodes[j].get('name', f'node{j}') if j < len(nodes) else f'missing{j}' for j in joints]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if len(joints) < 2:
        problems.append(f'skeleton has {len(joints)} joints; minimum 2')
    if len(joints) > MODEL_MAX_JOINTS:
        problems.append(f'{len(joints)} joints exceeds UniMate budget of {MODEL_MAX_JOINTS}')
    if duplicates:
        problems.append('duplicate joint node names collapse upstream: ' + ','.join(duplicates[:6]))
    joint_set = set(joints)
    parents = {}
    for index, node in enumerate(nodes):
        for child in node.get('children') or []:
            parents[child] = index
    roots = [j for j in joints if parents.get(j) not in joint_set]
    if len(roots) != 1:
        problems.append(f'skeleton must have exactly one root bone; found {len(roots)}')
    attrs = {a for mesh in doc.get('meshes') or [] for p in mesh.get('primitives') or []
             for a in (p.get('attributes') or {})}
    if not {'JOINTS_0', 'WEIGHTS_0'} <= attrs:
        problems.append('missing JOINTS_0/WEIGHTS_0: mesh is not skinned')
    return {'ok': not problems, 'problems': problems, 'joints': len(joints),
            'duplicates': duplicates, 'roots': len(roots)}


class UnimateBackend:
    id = 'unimate'
    kind = 'generate'

    def paths(self):
        repo = Path(os.environ.get('OPENFIGURA_UNIMATE_HOME',
                                   str(Path.home() / 'Desktop/Local/Opensource/UniMate')))
        python = Path(os.environ.get('OPENFIGURA_UNIMATE_PYTHON', str(repo / 'env/bin/python')))
        ckpt = Path(os.environ.get('OPENFIGURA_UNIMATE_CKPT',
                                   str(repo / 'outputs/unimate_uniml3d_f60_v3')))
        return repo, python, ckpt

    def blender_binary(self):
        from openfigura.backends.blender import BlenderBackend
        return BlenderBackend().binary()

    def capabilities(self) -> Capabilities:
        repo, python, ckpt = self.paths()
        missing = []
        if not (repo / 'unimate' / 'inference').is_dir():
            missing.append('UniMate checkout (set OPENFIGURA_UNIMATE_HOME)')
        if not python.is_file():
            missing.append('python runtime (set OPENFIGURA_UNIMATE_PYTHON)')
        if not (ckpt / 'config.json').is_file():
            missing.append('checkpoint dir (set OPENFIGURA_UNIMATE_CKPT)')
        if not (ckpt / 'checkpoints').is_dir():
            missing.append('checkpoint files')
        if not self.blender_binary():
            missing.append('Blender executable for mesh driving')
        if not (repo / 'data_process/mesh_animation/animate_motion.py').is_file():
            missing.append('UniMate animate_motion.py entry point')
        if missing:
            return Capabilities(False, hardware='cuda', reason='missing: ' + '; '.join(missing),
                                notes=self._notes())
        probe = base.run([str(python), '-c',
                         'import torch,torch_geometric,torchdiffeq;print("UNIMATE_READY",torch.__version__,"CUDA",torch.cuda.is_available())'],
                         timeout_s=120)
        ready = probe.ok and 'UNIMATE_READY' in probe.stdout_tail and 'CUDA True' in probe.stdout_tail
        return Capabilities(ready, hardware='cuda' if ready else 'cpu',
                            reason='' if ready else 'CUDA runtime with torch/torch_geometric required: '
                                   + (probe.stderr_tail or probe.stdout_tail),
                            notes=self._notes())

    def _notes(self):
        _, _, ckpt = self.paths()
        return {'upstream': 'UniMate @ github.com/Friedrich-M/UniMate (MIT code)',
                'weights_license': WEIGHTS_LICENSE,
                'binary_version': 'ckpt=' + str(ckpt),
                'opt_in': 'accept_nc_license must be passed explicitly per call',
                'length': '60 frames @ 30 fps per clip (upstream config)',
                'collision': 'upstream has no collision machinery; OpenFigura motion-gate decides pass',
                'pipeline': 'selected Python: rig_preprocess -> inference.sample -> sample_manifest validation; detected Blender: animate_motion.py',
                'drive_runtime': 'Blender uses its bundled Python and requires upstream animation dependencies; no conda activation or bare python shell calls.'}

    def preflight_rig(self, path: Path) -> dict:
        return preflight_rig(path)

    def generate_motion(self, model: Path, workdir: Path, prompt: str, repetitions: int,
                        cfg_scale: float, seed: int, annotation: str | None = None) -> dict:
        repo, python, ckpt = self.paths()
        model = Path(model).resolve()
        workdir = Path(workdir).resolve()
        workdir.mkdir(parents=True, exist_ok=False)
        asset = workdir / 'asset'
        samples = workdir / 'samples'
        steps = {}
        pre = [str(python), '-m', 'data_process.rig_preprocess.cli', '--input', str(model),
               '--output_dir', str(asset), '--annotate', 'rule', '--formats', 'glb,fbx']
        if annotation:
            pre += ['--annotation', str(Path(annotation).resolve())]
        preprocess = base.run(pre, timeout_s=900, cwd=repo)
        steps['rig_preprocess'] = {**preprocess.ledger(), 'stdout_tail': preprocess.stdout_tail}
        if not preprocess.ok:
            return {'produced': False, 'status': 'fail', 'steps': steps,
                    'stderr_tail': preprocess.stderr_tail}
        if not annotation:
            review = asset / 'REVIEW.md'
            if review.exists() or (asset / 'annotation.json').exists():
                return {'produced': False, 'status': 'awaiting_review', 'steps': steps,
                        'review': str(review if review.exists() else asset),
                        'note': 'upstream stops for joint-label/facing review; rerun with annotation=<file>'}
        sample = base.run([str(python), '-m', 'unimate.inference.sample',
                           '--exp_dir', str(ckpt), '--asset', str(asset), '--prompt', prompt,
                           '--num_repetitions', str(repetitions), '--cfg_scale', str(cfg_scale),
                           '--seed', str(seed), '--output_dir', str(samples)],
                          timeout_s=3600, cwd=repo)
        steps['sample'] = {**sample.ledger(), 'stdout_tail': sample.stdout_tail}
        if not sample.ok:
            return {'produced': False, 'status': 'fail', 'steps': steps,
                    'stderr_tail': sample.stderr_tail}
        blender = self.blender_binary()
        if not blender:
            return {'produced': False, 'status': 'unavailable', 'steps': steps,
                    'stderr_tail': 'Blender executable unavailable for mesh driving'}
        # Keep the complete upstream job list in a file, rather than the ledger's
        # truncated stdout tail. The upstream module owns joint/frame validation.
        job_path = workdir / 'drive-jobs.tsv'
        manifest_code = (
            'import contextlib,sys; '
            'from data_process.mesh_animation.sample_manifest import main; '
            'stream=open(sys.argv[2],"w",encoding="utf-8"); '
            '\nwith stream,contextlib.redirect_stdout(stream):\n'
            '    code=main([sys.argv[1]])\n'
            'sys.exit(code)')
        manifest = base.run([str(python), '-c', manifest_code, str(samples), str(job_path)],
                            timeout_s=300, cwd=repo)
        steps['manifest'] = {**manifest.ledger(), 'stdout_tail': manifest.stdout_tail}
        if not manifest.ok:
            return {'produced': False, 'status': 'fail', 'steps': steps,
                    'stderr_tail': manifest.stderr_tail}
        try:
            jobs = [line.split('\t') for line in job_path.read_text(encoding='utf-8').splitlines() if line]
            if not jobs or any(len(job) != 4 for job in jobs):
                raise ValueError('manifest emitted no jobs or invalid TSV')
            stems = set()
            for index, (anim, char, cond, dtype) in enumerate(jobs):
                # Upstream records asset/cond paths relative to its repository.
                anim, char, cond = [str((repo / p).resolve()) if not Path(p).is_absolute()
                                   else str(Path(p).resolve()) for p in (anim, char, cond)]
                jobs[index] = [anim, char, cond, dtype]
                if dtype not in {'general', 'truebones', 'mixamo', 'objaverse'}:
                    raise ValueError('manifest emitted unsupported dataset type')
                if any(not Path(p).is_file() for p in (anim, char, cond)):
                    raise ValueError('manifest job inputs are missing')
                stem = Path(anim).stem
                if stem in stems: raise ValueError('manifest job output names collide')
                stems.add(stem)
        except (OSError, ValueError) as exc:
            return {'produced': False, 'status': 'fail', 'steps': steps, 'stderr_tail': str(exc)}
        clips = []
        drive_steps = []
        animated = samples / 'animated'
        animated.mkdir(parents=True, exist_ok=False)
        for anim, char, cond, dtype in jobs:
            drive = base.run([str(blender), '-b', '--factory-startup', '--python-exit-code', '1',
                              '--python', str(repo / 'data_process/mesh_animation/animate_motion.py'), '--',
                              '--dataset_type', dtype, '--anim_path', anim, '--char_path', char,
                              '--cond_path', cond, '--output_dir', str(animated), '--anim_mode', 'fk',
                              '--asset', 'canonical', '--extra_bones_strategy', 'merge'],
                             timeout_s=1800, cwd=repo)
            drive_steps.append({**drive.ledger(), 'stdout_tail': drive.stdout_tail})
            clip = animated / (Path(anim).stem + '.glb')
            fbx = clip.with_suffix('.fbx')
            if not drive.ok or not clip.is_file() or not fbx.is_file():
                steps['drive'] = {'jobs': drive_steps, 'exit_code': drive.exit_code or 1}
                return {'produced': False, 'status': 'fail', 'steps': steps, 'clips': [],
                        'stderr_tail': drive.stderr_tail or 'Blender did not produce expected GLB and FBX'}
            clips.append(str(clip))
        steps['drive'] = {'jobs': drive_steps, 'exit_code': 0,
                          'wall_seconds': round(sum(s['wall_seconds'] for s in drive_steps), 2)}
        return {'produced': True, 'status': 'pass', 'clips': clips, 'steps': steps, 'stderr_tail': ''}


registry.register('unimate', UnimateBackend,
                  'external UniMate text-to-motion (CC BY-NC weights; opt-in per call)')
