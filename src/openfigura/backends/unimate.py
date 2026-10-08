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
                'pipeline': 'rig_preprocess --annotate rule -> inference.sample -> run_animate_motion.sh'}

    def preflight_rig(self, path: Path) -> dict:
        return preflight_rig(path)

    def generate_motion(self, model: Path, workdir: Path, prompt: str, repetitions: int,
                        cfg_scale: float, seed: int, annotation: str | None = None) -> dict:
        repo, python, ckpt = self.paths()
        model = Path(model).resolve()
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=False)
        asset = workdir / 'asset'
        samples = workdir / 'samples'
        steps = {}
        pre = [str(python), '-m', 'data_process.rig_preprocess.cli', '--input', str(model),
               '--output_dir', str(asset), '--annotate', 'rule', '--formats', 'glb,fbx']
        if annotation:
            pre += ['--annotation', str(Path(annotation).resolve())]
        steps['rig_preprocess'] = base.run(pre, timeout_s=900, cwd=repo).ledger()
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
        drive = base.run(['bash', 'scripts/run_animate_motion.sh', str(samples)],
                         timeout_s=1800, cwd=repo)
        steps['drive'] = {**drive.ledger(), 'stdout_tail': drive.stdout_tail}
        clips = sorted(p for p in samples.rglob('*.glb') if p.is_file())
        return {'produced': bool(clips) and drive.ok, 'status': 'pass' if clips and drive.ok else 'fail',
                'clips': [str(p) for p in clips], 'steps': steps,
                'stderr_tail': drive.stderr_tail if not drive.ok else ''}


registry.register('unimate', UnimateBackend,
                  'external UniMate text-to-motion (CC BY-NC weights; opt-in per call)')
