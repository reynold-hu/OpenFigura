import json

from openfigura.cli import main
from openfigura.core import engine
from openfigura.core.task import Task


def request():
    return {'step': 'generate', 'inputs': [], 'params': {'seed': 42},
            'backend': 'pixal3d', 'backend_version': 'trial-v1'}


def test_cli_records_request_but_does_not_run_backend(tmp_path, capsys):
    task = Task.create(tmp_path / 'tasks')
    spec = tmp_path / 'request.json'
    spec.write_text(json.dumps(request()))
    assert main(['workflow-submit', str(task.root), '--spec', str(spec)]) == 0
    stage = json.loads(capsys.readouterr().out)
    assert stage['status'] == 'queued'
    assert not task.artifact('model.glb').exists()
    assert main(['workflow-status', str(task.root)]) == 0
    snapshot = json.loads(capsys.readouterr().out)
    assert snapshot == engine.workflow_status(Task.open(task.root))
    assert main(['workflow-cancel', str(task.root), stage['stage_id']]) == 0
    cancelled = json.loads(capsys.readouterr().out)
    assert cancelled['status'] == 'cancelled'
    assert main(['workflow-resume', str(task.root), stage['stage_id']]) == 0
    resumed = json.loads(capsys.readouterr().out)
    assert resumed['status'] == 'queued'
    assert resumed['stage_id'] != stage['stage_id']


def test_bad_request_cannot_create_stage(tmp_path):
    import pytest
    task = Task.create(tmp_path)
    bad = request()
    bad['unexpected'] = 'ignore me'
    with pytest.raises(ValueError):
        engine.workflow_submit(task, bad)


def test_real_mcp_workflow_status_matches_core(tmp_path):
    import asyncio
    import pytest
    pytest.importorskip('mcp')
    from openfigura.mcp_server import build
    task = Task.create(tmp_path)
    async def run():
        app = build()
        result = await app.call_tool('figura_workflow_submit',
                                     {'task_root': str(task.root), 'request': request()})
        if hasattr(result, 'is_error'):
            assert not result.is_error
        else:
            assert not getattr(result, 'isError', False)
        result = await app.call_tool('figura_workflow_status', {'task_root': str(task.root)})
        if hasattr(result, 'content'):
            return json.loads(result.content[0].text)
        return result[1]
    assert asyncio.run(run()) == engine.workflow_status(Task.open(task.root))
