import ast
import json
import struct
from pathlib import Path

import pytest

from openfigura.backends.rig_transfer import RigTransferBackend
from openfigura.core import engine, registry
from openfigura.core.task import Task, sha256_file
from openfigura.core.registry import Capabilities
from test_engine import make_minimal_glb, make_minimal_glb_from
from test_rig import skinned_glb


def skinned_static_glb(path):
    """A skinned GLB with no animation clips — the shape the real transfer worker
    exports (export_animations=False)."""
    skinned_glb(path)
    data = path.read_bytes()
    doc = json.loads(data[20:20 + struct.unpack_from('<I', data, 12)[0]])
    doc.pop('animations', None)
    make_minimal_glb_from(path, doc)


def _worker_functions():
    worker = Path(__file__).parents[1] / 'src/openfigura/backends/rig_transfer_worker.py'
    tree = ast.parse(worker.read_text())
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('blend', 'barycentric')]
    ns = {}
    exec(compile(ast.Module(body=funcs, type_ignores=[]), str(worker), 'exec'), ns)
    return ns


def test_blend_interpolates_and_renormalises():
    ns = _worker_functions()
    result = dict(ns['blend']({'Spine': 1.0}, {'Arm': 1.0}, {}, 0.5, 0.5, 0.0))
    assert result == {'Spine': 0.5, 'Arm': 0.5}


def test_blend_keeps_top_influences_and_normalises():
    ns = _worker_functions()
    out = ns['blend']({'a': 0.4, 'b': 0.3, 'c': 0.3}, {}, {}, 1.0, 0.0, 0.0, limit=2)
    assert len(out) == 2 and abs(sum(w for _, w in out) - 1.0) < 1e-9
    assert dict(out)['a'] == 0.4 / 0.7


def test_blend_empty_returns_none_weights():
    assert _worker_functions()['blend']({}, {}, {}, 1, 0, 0) == []


def test_barycentric_recovers_vertices():
    ns = _worker_functions()
    class V(tuple):
        def __sub__(self, o): return V(a - b for a, b in zip(self, o))
        def dot(self, o): return sum(a * b for a, b in zip(self, o))
    a, b, c = V((0, 0, 0)), V((1, 0, 0)), V((0, 1, 0))
    assert ns['barycentric'](a, a, b, c) == pytest.approx((1, 0, 0), abs=1e-6)
    assert ns['barycentric'](b, a, b, c) == pytest.approx((0, 1, 0), abs=1e-6)
    assert ns['barycentric'](V((1/3, 1/3, 0)), a, b, c) == pytest.approx((1/3, 1/3, 1/3), abs=1e-6)


def test_backend_missing_binary_is_truthful(monkeypatch):
    monkeypatch.setattr(RigTransferBackend, 'binary', lambda self: None)
    assert not RigTransferBackend().capabilities().available


@pytest.mark.parametrize('params', [{'max_influences': 0}, {'max_influences': 9},
                                    {'max_influences': True}, {'refuse_distance_ratio': 0},
                                    {'refuse_distance_ratio': 0.6}, {'refuse_distance_ratio': float('nan')}])
def test_invalid_params_before_subprocess(tmp_path, monkeypatch, params):
    monkeypatch.setattr(RigTransferBackend, 'binary', lambda self: '/fake/blender')
    t = tmp_path / 't.glb'; s = tmp_path / 's.glb'
    t.write_bytes(b'x'); s.write_bytes(b'x')
    with pytest.raises(ValueError):
        RigTransferBackend().transfer(t, s, tmp_path / 'o.glb', params)


def test_transfer_refuses_same_and_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(RigTransferBackend, 'binary', lambda self: '/fake/blender')
    t = tmp_path / 't.glb'; t.write_bytes(b'x')
    with pytest.raises(ValueError):
        RigTransferBackend().transfer(t, t, tmp_path / 'o.glb', {})
    out = tmp_path / 'o.glb'; out.write_bytes(b'exists')
    with pytest.raises(ValueError):
        RigTransferBackend().transfer(t, tmp_path / 's.glb', out, {})
    (tmp_path / 's.glb').write_bytes(b'x')


def _wire_engine(tmp_path, monkeypatch, joint_count=1, produced_exit=0, clip=False):
    task = Task.create(tmp_path / 'tasks', name='xfer')
    make_minimal_glb(task.artifact('model.glb'))
    skinned_glb(task.artifact('model-autorig.glb'))
    class FakeTransfer:
        id = 'blender-rig-transfer'
        def capabilities(self): return Capabilities(True, hardware='cpu')
        def transfer(self, target, source, output, params):
            skinned_static_glb(output)
            if clip:
                data = output.read_bytes()
                doc = json.loads(data[20:20 + struct.unpack_from('<I', data, 12)[0]])
                doc['animations'] = [{'name': 'Fabricated', 'channels': []}]
                make_minimal_glb_from(output, doc)
            output.with_suffix('.rig-transfer-report.json').write_text(json.dumps({'vertices': 3, 'vertices_without_weights': 0}))
            return {'backend': self.id, 'exit_code': produced_exit, 'wall_seconds': 0.5,
                    'command': 'fake', 'stderr_tail': 'boom', 'report': {'vertices': 3, 'vertices_without_weights': 0},
                    'output': str(output), 'report_path': str(output.with_suffix('.rig-transfer-report.json'))}
    monkeypatch.setattr(registry, 'get', lambda name: FakeTransfer())
    return task


def test_transfer_rig_verb_passes_and_preserves_inputs(tmp_path, monkeypatch):
    task = _wire_engine(tmp_path, monkeypatch)
    t_sha = sha256_file(task.artifact('model.glb'))
    s_sha = sha256_file(task.artifact('model-autorig.glb'))
    result = engine.transfer_rig(task, 'model-autorig.glb', artifact='model.glb')
    assert result['status'] == 'pass' and result['joint_count'] == 1
    assert result['visual_approval'] == 'pending'
    assert sha256_file(task.artifact('model.glb')) == t_sha
    assert sha256_file(task.artifact('model-autorig.glb')) == s_sha
    assert Task.open(task.root).entries[-1]['step'] == 'transfer_rig'


def test_transfer_rig_rejects_rigged_target(tmp_path, monkeypatch):
    task = _wire_engine(tmp_path, monkeypatch)
    skinned_glb(task.artifact('model.glb'))
    with pytest.raises(ValueError, match='static'):
        engine.transfer_rig(task, 'model-autorig.glb', artifact='model.glb')


def test_transfer_rig_rejects_static_source(tmp_path, monkeypatch):
    task = _wire_engine(tmp_path, monkeypatch)
    make_minimal_glb(task.artifact('plain.glb'))
    with pytest.raises(ValueError, match='skeleton'):
        engine.transfer_rig(task, 'plain.glb', artifact='model.glb')


def test_transfer_rig_refuses_fabricated_clips(tmp_path, monkeypatch):
    task = _wire_engine(tmp_path, monkeypatch, clip=True)
    with pytest.raises(RuntimeError, match='animation clips'):
        engine.transfer_rig(task, 'model-autorig.glb')


def test_execute_transfer_rig_step(tmp_path, monkeypatch):
    from openfigura.core.contracts import AssetRef
    task = Task.create(tmp_path / 'tasks')
    make_minimal_glb(task.artifact('model.glb'))
    skinned_glb(task.artifact('model-autorig.glb'))
    class FakeTransfer:
        id = 'blender-rig-transfer'
        def capabilities(self): return Capabilities(True, hardware='cpu')
        def transfer(self, target, source, output, params):
            skinned_static_glb(output)
            output.with_suffix('.rig-transfer-report.json').write_text(json.dumps({'vertices': 3, 'vertices_without_weights': 0}))
            return {'backend': self.id, 'exit_code': 0, 'wall_seconds': 0.5, 'command': 'c',
                    'stderr_tail': '', 'report': {'vertices': 3, 'vertices_without_weights': 0}, 'output': str(output),
                    'report_path': str(output.with_suffix('.rig-transfer-report.json'))}
    monkeypatch.setattr(registry, 'get', lambda name: FakeTransfer())
    refs = [AssetRef('artifacts/model.glb', sha256_file(task.artifact('model.glb')), 'model', 'import').to_dict(),
            AssetRef('artifacts/model-autorig.glb', sha256_file(task.artifact('model-autorig.glb')), 'model', 'import').to_dict()]
    result = engine.execute(task, 'transfer_rig', refs,
                            {'source': 'model-autorig.glb', 'artifact': 'model.glb'})
    assert result['status'] == 'pass' and result['backend'] == 'blender-rig-transfer'
    assert any(o['kind'] == 'model' and 'transferred' in o['task_relative_path'] for o in result['outputs'])
