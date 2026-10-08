import json
from pathlib import Path

import pytest

from openfigura.backends.unimate import preflight_rig
from openfigura.core import engine, registry
from openfigura.core.contracts import AssetRef
from openfigura.core.task import Task, sha256_file
from test_engine import make_minimal_glb_from, make_minimal_glb
from test_rig import skinned_glb


def chain_glb(path, joints, names=None, duplicates=False):
    """Skinned GLB with a linear bone chain of `joints` nodes."""
    make_minimal_glb(path)
    import struct
    data = path.read_bytes()
    doc = json.loads(data[20:20 + struct.unpack_from('<I', data, 12)[0]])
    doc['meshes'][0]['primitives'][0]['attributes'].update(JOINTS_0=3, WEIGHTS_0=4)
    names = names or [f'bone{i}' for i in range(joints)]
    if duplicates and joints >= 2:
        names[1] = names[0]
    nodes = [{'mesh': 0, 'skin': 0, 'children': [1]}]
    for i in range(joints):
        node = {'name': names[i]}
        if i + 1 < joints:
            node['children'] = [i + 2]
        nodes.append(node)
    doc['nodes'] = nodes
    doc['skins'] = [{'joints': list(range(1, joints + 1)), 'skeleton': 1}]
    make_minimal_glb_from(path, doc)


def test_preflight_accepts_clean_chain(tmp_path):
    p = tmp_path / 'm.glb'
    chain_glb(p, 3)
    assert preflight_rig(p) == {'ok': True, 'problems': [], 'joints': 3, 'duplicates': [], 'roots': 1}


def test_preflight_flags_duplicates_budget_and_skin(tmp_path):
    dup = tmp_path / 'd.glb'; chain_glb(dup, 3, duplicates=True)
    result = preflight_rig(dup)
    assert not result['ok'] and any('duplicate' in x for x in result['problems'])
    big = tmp_path / 'b.glb'; chain_glb(big, 72)
    assert any('71' in x for x in preflight_rig(big)['problems'])
    bare = tmp_path / 'n.glb'; make_minimal_glb(bare)
    assert not preflight_rig(bare)['ok'] and any('no skin' in x for x in preflight_rig(bare)['problems'])


def test_preflight_rejects_multi_root(tmp_path):
    p = tmp_path / 'm.glb'
    chain_glb(p, 2)
    import struct
    data = p.read_bytes(); doc = json.loads(data[20:20 + struct.unpack_from('<I', data, 12)[0]])
    for node in doc['nodes']:
        node.pop('children', None)
    doc['nodes'][0]['children'] = [1, 2]
    make_minimal_glb_from(p, doc)
    assert not preflight_rig(p)['ok']


class FakeUnimate:
    def __init__(self, clips=None, status='pass'):
        self.clips = clips or []
        self.status = status
    def capabilities(self):
        return registry.Capabilities(True, hardware='cuda', notes={'version': 'test'})
    def preflight_rig(self, path):
        return {'ok': True, 'problems': [], 'joints': 3, 'duplicates': [], 'roots': 1}
    def generate_motion(self, model, workdir, prompt, repetitions, cfg_scale, seed, annotation=None):
        workdir.mkdir(parents=True, exist_ok=True)
        made = []
        for i, name in enumerate(self.clips):
            clip = workdir / name
            skinned_glb(clip)
            made.append(str(clip))
        return {'produced': bool(made), 'status': self.status, 'clips': made,
                'steps': {'sample': {'exit_code': 0}}, 'stderr_tail': ''}


class FakeGate:
    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.n = 0
    def gate(self, clip, report_path, regions=None, margin=0.002):
        status = self.statuses[min(self.n, len(self.statuses) - 1)]
        self.n += 1
        report = {'status': status, 'summary': {'crossing_rows': 0 if status == 'pass' else 1}}
        Path(report_path).write_text(json.dumps(report), encoding='utf-8')
        return {'exit_code': 0, 'report': report, 'report_path': str(report_path), 'stderr_tail': ''}


def rigged_task(tmp_path):
    task = Task.create(tmp_path / 'tasks', name='anim')
    skinned_glb(task.artifact('model-autorig.glb'))
    return task


def wire(monkeypatch, clips, statuses):
    unimate, gate = FakeUnimate(clips=clips), FakeGate(statuses)
    monkeypatch.setattr(registry, 'get', lambda name: gate if name == 'blender-motion-gate' else unimate)
    return unimate, gate


def test_unimate_weights_license_blocks_before_any_motion(tmp_path, monkeypatch):
    task = rigged_task(tmp_path)
    wire(monkeypatch, ['clip-0.glb'], ['pass'])
    with pytest.raises(RuntimeError, match='CC BY-NC'):
        engine.animate(task, 'An object walks forward.', accept_nc_license=False)
    assert not (task.root / 'motion').exists()
    assert Task.open(task.root).entries[-1]['status'] == 'blocked'


def test_gate_selects_only_passing_clip_and_records_provenance(tmp_path, monkeypatch):
    task = rigged_task(tmp_path)
    wire(monkeypatch, ['clip-0.glb', 'clip-1.glb'], ['fail', 'pass'])
    result = engine.animate(task, 'An object runs forward.', accept_nc_license=True)
    assert result['status'] == 'pass' and result['delivered_clip'].endswith('clip-1.glb')
    assert result['weights_license_accepted'] is True and result['visual_approval'] == 'pending'
    assert task.artifact('model-motion.glb').is_file()
    verdicts = result['gate']
    assert [v['status'] for v in verdicts] == ['fail', 'pass']
    assert all(Path(task.root / v['report']).is_file() for v in verdicts)


def test_all_clips_rejected_quarantines_and_fails(tmp_path, monkeypatch):
    task = rigged_task(tmp_path)
    wire(monkeypatch, ['clip-0.glb', 'clip-1.glb'], ['fail', 'fail'])
    with pytest.raises(RuntimeError, match='contact gate'):
        engine.animate(task, 'An object jumps.', accept_nc_license=True)
    assert not task.artifact('model-motion.glb').exists()
    rejected = list((task.root / 'artifacts' / 'rejected').rglob('*.glb'))
    assert rejected and 'clip' in rejected[0].name
    assert Task.open(task.root).entries[-1]['status'] == 'fail'


def test_preflight_failure_stops_before_backend(tmp_path, monkeypatch):
    task = rigged_task(tmp_path)
    monkeypatch.setattr(registry, 'get', lambda name: None)
    class BadPreflight(FakeUnimate):
        def preflight_rig(self, path):
            return {'ok': False, 'problems': ['duplicate joint names'], 'joints': 5,
                    'duplicates': ['x'], 'roots': 1}
    monkeypatch.setattr(registry, 'get',
                        lambda name: FakeGate(['pass']) if name == 'blender-motion-gate' else BadPreflight(clips=['c.glb']))
    with pytest.raises(RuntimeError, match='preflight'):
        engine.animate(task, 'p', accept_nc_license=True)
    assert Task.open(task.root).entries[-1]['step'] == 'motion-preflight'


def test_unavailable_backend_reports_honest_reason(tmp_path, monkeypatch):
    task = rigged_task(tmp_path)
    class Unavailable:
        def capabilities(self):
            return registry.Capabilities(False, reason='missing: python runtime')
    monkeypatch.setattr(registry, 'get', lambda name: Unavailable())
    with pytest.raises(RuntimeError, match='unavailable: missing'):
        engine.animate(task, 'p', accept_nc_license=True)


@pytest.mark.parametrize('kwargs', [
    {'prompt': ''}, {'prompt': 5}, {'repetitions': 0}, {'repetitions': 9},
    {'cfg_scale': 99}, {'cfg_scale': float('nan')}, {'seed': -1}, {'annotation': 7}])
def test_animate_parameter_validation(tmp_path, kwargs):
    task = rigged_task(tmp_path)
    args = {'prompt': 'An object walks.', 'repetitions': 3, 'cfg_scale': 3.0, 'seed': 42}
    args.update(kwargs)
    with pytest.raises(ValueError):
        engine.animate(task, **args, accept_nc_license=True)


def test_execute_animate_step_uses_backend_and_gate(tmp_path, monkeypatch):
    task, refs = _rig_refs(tmp_path)
    wire(monkeypatch, ['clip-0.glb'], ['pass'])
    result = engine.execute(task, 'animate', refs, {'prompt': 'An object walks forward.',
                                                    'accept_nc_license': True})
    assert result['status'] == 'pass' and result['backend'] == 'unimate'
    kinds = {r['kind'] for r in result['outputs']}
    assert 'model' in kinds and 'report' in kinds


def _rig_refs(tmp_path):
    task = Task.create(tmp_path / 'tasks')
    skinned_glb(task.artifact('model-autorig.glb'))
    ref = AssetRef('artifacts/model-autorig.glb', sha256_file(task.artifact('model-autorig.glb')),
                   'model', 'import').to_dict()
    return task, [ref]
