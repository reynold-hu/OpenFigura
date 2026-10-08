import asyncio
import json

import pytest

from openfigura.backends.mesh_tools import MeshToolsBackend
from openfigura.core import registry
from openfigura.cli import main
from openfigura.core import engine
from openfigura.core.contracts import AssetRef
from openfigura.core.task import Task, sha256_file
from test_engine import make_minimal_glb


def imported(tmp_path):
    task = Task.create(tmp_path / 'tasks')
    path = task.artifact('model.glb')
    make_minimal_glb(path)
    return task, [AssetRef('artifacts/model.glb', sha256_file(path), 'model', 'import').to_dict()]


def test_mesh_backend_is_registered():
    assert 'blender-mesh-tools' in registry.available()


def test_mesh_verb_records_hashes_and_refuses_second_candidate(tmp_path, monkeypatch):
    task, _ = imported(tmp_path)
    monkeypatch.setattr(MeshToolsBackend, 'binary', lambda self: '/fake/blender')
    def fake_process(self, model, output, operation, params):
        assert operation == 'optimize'
        output.write_bytes(b'candidate')
        output.with_suffix('.mesh-report.json').write_text(json.dumps({'operation': operation}))
        return {'backend': self.id, 'exit_code': 0, 'wall_seconds': 0.1,
                'stdout_tail': '', 'stderr_tail': '', 'report': {'operation': operation}}
    monkeypatch.setattr(MeshToolsBackend, 'process', fake_process)
    result = engine.mesh(task, 'optimize', {'ratio': 0.5})
    assert result['status'] == 'pass'
    assert result['output_sha256'] == sha256_file(task.artifact('model-optimize.glb'))
    assert result['visual_approval'] == 'pending'
    assert json.loads((task.root / 'provenance.json').read_text())['entries'][-1]['step'] == 'mesh'
    with pytest.raises(FileExistsError):
        engine.mesh(task, 'optimize', {'ratio': 0.5})


def test_cli_mesh_and_execute_share_engine_verb(tmp_path, monkeypatch, capsys):
    task, refs = imported(tmp_path)
    monkeypatch.setattr(MeshToolsBackend, 'binary', lambda self: '/fake/blender')
    def fake_process(self, model, output, operation, params):
        output.write_bytes(b'candidate')
        output.with_suffix('.mesh-report.json').write_text(json.dumps({'operation': operation}))
        return {'backend': self.id, 'exit_code': 0, 'wall_seconds': 0.1,
                'stdout_tail': '', 'stderr_tail': '', 'report': {'operation': operation}}
    monkeypatch.setattr(MeshToolsBackend, 'process', fake_process)
    assert main(['mesh', str(task.root), '--operation', 'optimize',
                 '--params', '{"ratio": 0.5}']) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'pass'
    inputs = tmp_path / 'inputs.json'
    inputs.write_text(json.dumps(refs))
    assert main(['execute', str(task.root), '--step', 'inspect', '--inputs', f'@{inputs}']) == 0
    cli_result = json.loads(capsys.readouterr().out)
    assert cli_result['status'] == 'pass'
    report = next(AssetRef.from_dict(r) for r in cli_result['outputs'] if r['kind'] == 'report')
    assert json.loads(report.verify(task.root).read_text())['ok']


def test_mcp_execute_mirrors_cli_result(tmp_path):
    pytest.importorskip('mcp')
    from openfigura.mcp_server import build
    task, refs = imported(tmp_path)
    async def run():
        app = build()
        result = await app.call_tool('figura_execute', {
            'task_root': str(task.root), 'step': 'inspect', 'inputs': refs, 'params': {}})
        if hasattr(result, 'is_error'):
            assert not result.is_error
        else:
            assert not getattr(result, 'isError', False)
        if hasattr(result, 'content'):
            return json.loads(result.content[0].text)
        return result[1]
    mcp_result = asyncio.run(run())
    assert mcp_result['status'] == 'pass'
    assert mcp_result['cached_from'] is None
    stage = engine.workflow_status(Task.open(task.root), mcp_result['stage_id'])
    assert stage['status'] == 'pass'
    second = asyncio.run(run())
    assert second['cached_from'] == mcp_result['stage_id']
