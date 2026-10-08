import json

import pytest

from openfigura.core import engine, registry
from openfigura.core.contracts import AssetRef
from openfigura.core.task import Task, sha256_file
from test_engine import make_minimal_glb


class FakeBake:
    id = 'blender-bake'
    def capabilities(self):
        return registry.Capabilities(True, hardware='cpu')
    def bake(self, high, low, output, params):
        make_minimal_glb(output)
        blend = output.with_suffix('.blend')
        blend.write_bytes(b'blend fixture')
        textures = {}
        for kind in params.get('maps', ['normal', 'ao']):
            path = output.with_name(output.stem + '-' + kind + '.png')
            path.write_bytes(b'\x89PNG\r\n\x1a\nfixture')
            textures[kind] = str(path)
        report = output.with_suffix('.bake-report.json')
        report.write_text(json.dumps({'uv_preserved': True, 'target_triangles': 1, 'result_triangles': 1}))
        return {'exit_code': 0, 'produced': True, 'report_path': str(report),
                'report': json.loads(report.read_text()), 'textures': textures, 'blend': str(blend)}


def task_with_sources(tmp_path, monkeypatch):
    task = Task.create(tmp_path / 'tasks')
    for name in ('high.glb', 'low.glb'):
        make_minimal_glb(task.artifact(name))
    monkeypatch.setattr(registry, 'get', lambda name: FakeBake())
    return task


def test_bake_preserves_sources_and_emits_declared_artifacts(tmp_path, monkeypatch):
    task = task_with_sources(tmp_path, monkeypatch)
    high = sha256_file(task.artifact('high.glb'))
    low = sha256_file(task.artifact('low.glb'))
    result = engine.bake(task, 'high.glb', 'low.glb')
    assert result['status'] == 'pass' and result['visual_approval'] == 'pending'
    assert sha256_file(task.artifact('high.glb')) == high
    assert sha256_file(task.artifact('low.glb')) == low
    assert task.artifact('model-baked.blend').is_file()


def test_execute_bake_returns_textures_and_blend(tmp_path, monkeypatch):
    task = task_with_sources(tmp_path, monkeypatch)
    refs = [AssetRef('artifacts/' + name, sha256_file(task.artifact(name)), 'model', 'import').to_dict()
            for name in ('high.glb', 'low.glb')]
    result = engine.execute(task, 'bake', refs, {'source': 'high.glb', 'artifact': 'low.glb'})
    assert result['status'] == 'pass'
    assert {'model', 'texture', 'blend', 'report'} <= {ref['kind'] for ref in result['outputs']}


def test_bake_failure_has_no_exportable_candidate(tmp_path, monkeypatch):
    task = task_with_sources(tmp_path, monkeypatch)
    class Failed(FakeBake):
        def bake(self, *args, **kwargs):
            result = super().bake(*args, **kwargs)
            result['produced'] = False
            result['exit_code'] = 1
            return result
    monkeypatch.setattr(registry, 'get', lambda name: Failed())
    with pytest.raises(RuntimeError):
        engine.bake(task, 'high.glb', 'low.glb')
    assert not task.artifact('model-baked.glb').exists()


def test_bake_can_create_materials_for_geometry_only_inputs(tmp_path, monkeypatch):
    import struct
    from test_engine import make_minimal_glb_from
    task = task_with_sources(tmp_path, monkeypatch)
    for name in ('high.glb','low.glb'):
        path = task.artifact(name)
        data = path.read_bytes()
        doc = json.loads(data[20:20 + struct.unpack_from('<I',data,12)[0]])
        doc.pop('materials',None)
        for mesh in doc['meshes']:
            for p in mesh['primitives']:
                p.pop('material',None)
        make_minimal_glb_from(path, doc)
    assert engine.bake(task, 'high.glb','low.glb')['status'] == 'pass'
