import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from openfigura.backends.mesh_tools import MeshToolsBackend


def test_missing_binary_truthful(monkeypatch):
    monkeypatch.setattr(MeshToolsBackend, 'binary', lambda self: None)
    assert not MeshToolsBackend().capabilities().available


@pytest.mark.parametrize('operation,params', [('bake', {}), ('optimize', {}), ('optimize', {'ratio': 0}), ('optimize', {'ratio': True}), ('retopo', {'target_faces': 1.5}), ('retopo', {'target_faces': True}), ('segment', {'max_parts': 0})])
def test_invalid_request_before_subprocess(tmp_path, monkeypatch, operation, params):
    source = tmp_path / 'source.glb'
    source.write_bytes(b'fixture')
    monkeypatch.setattr(MeshToolsBackend, 'binary', lambda self: '/fake/blender')
    with pytest.raises(ValueError):
        MeshToolsBackend().process(source, tmp_path / 'out.glb', operation, params)


def test_refuses_overwrite(tmp_path):
    source = tmp_path / 'source.glb'
    source.write_bytes(b'fixture')
    with pytest.raises(ValueError, match='overwrite'):
        MeshToolsBackend().process(source, source, 'uv', {})


def test_config_subprocess_report_and_cleanup(tmp_path, monkeypatch):
    source = tmp_path / 'source.glb'
    source.write_bytes(b'fixture')
    output = tmp_path / 'out.glb'
    configs = []
    def run(argv, **kwargs):
        cfgpath = Path(argv[-1]); configs.append(cfgpath)
        cfg = json.loads(cfgpath.read_text())
        assert argv[-2] == '--'
        assert cfg['operation'] == 'optimize'
        assert cfg['params']['ratio'] == 0.5
        Path(cfg['output']).write_bytes(b'new fixture')
        Path(cfg['report']).write_text(json.dumps({'operation': 'optimize', 'source': {'triangles': 12}, 'result': {'triangles': 6}}))
        return SimpleNamespace(returncode=0, stdout='done', stderr='')
    monkeypatch.setattr(MeshToolsBackend, 'binary', lambda self: '/fake/blender')
    monkeypatch.setattr('openfigura.backends.mesh_tools.subprocess.run', run)
    result = MeshToolsBackend().process(source, output, 'optimize', {'ratio': 0.5})
    assert result['exit_code'] == 0
    assert result['report']['result']['triangles'] == 6
    assert not configs[0].exists()
    assert source.read_bytes() == b'fixture'


def test_success_without_artifact_is_failure(tmp_path, monkeypatch):
    source = tmp_path / 'source.glb'; source.write_bytes(b'fixture')
    monkeypatch.setattr(MeshToolsBackend, 'binary', lambda self: '/fake/blender')
    monkeypatch.setattr('openfigura.backends.mesh_tools.subprocess.run', lambda *a, **k: SimpleNamespace(returncode=0, stdout='', stderr=''))
    result = MeshToolsBackend().process(source, tmp_path / 'out.glb', 'collision', {})
    assert result['exit_code'] != 0


def test_geometric_components_bridge_uv_duplicates_without_welding():
    import ast
    worker = Path(__file__).parents[1] / 'src/openfigura/backends/mesh_tools_worker.py'
    tree = ast.parse(worker.read_text())
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'component_groups']
    assert functions, 'component grouping helper is required'
    namespace = {}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(worker), 'exec'), namespace)
    mesh = SimpleNamespace(vertices=[SimpleNamespace(co=(0,0,0)), SimpleNamespace(co=(1,0,0)), SimpleNamespace(co=(1,0,0)), SimpleNamespace(co=(2,0,0)), SimpleNamespace(co=(9,0,0))], edges=[SimpleNamespace(vertices=(0,1)), SimpleNamespace(vertices=(2,3))])
    groups = namespace['component_groups'](mesh)
    assert sorted(map(len, groups)) == [1,4]
    assert len(mesh.vertices) == 5
