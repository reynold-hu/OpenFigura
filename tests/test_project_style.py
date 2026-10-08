import json

from openfigura.core import engine
from openfigura.core.task import Task
from openfigura.cli import main


def style():
    return dict(schema_version=1, canvas_width=64, canvas_height=64,
                pixel_scale=1, palette=['#000000', '#FFFFFF'],
                outline_policy='single_pixel', shading_policy='flat',
                fps=8, anchor='feet', transparent_background=True)


def test_style_cli_and_core_share_validated_contract(tmp_path, capsys):
    task = Task.create(tmp_path, name='style-task')
    config = tmp_path / 'style.json'
    config.write_text(json.dumps(style()))
    assert main(['set-style', str(task.root), '--spec', str(config)]) == 0
    cli = json.loads(capsys.readouterr().out)
    assert cli['style_spec'] == style()
    assert cli['visual_approval'] == 'pending'
    reopened = Task.open(task.root)
    assert reopened.entries[-1]['style_spec'] == style()
    assert engine.project_style(reopened)['style_spec'] == style()


def test_invalid_style_is_not_recorded(tmp_path):
    import pytest
    task = Task.create(tmp_path)
    spec = style()
    spec['fps'] = True
    with pytest.raises(ValueError):
        engine.set_style(task, spec)
    assert Task.open(task.root).entries == []


def test_missing_style_is_explicit(tmp_path):
    task = Task.create(tmp_path)
    assert engine.project_style(task) == {'status': 'unset', 'style_spec': None}


def test_two_open_clients_preserve_both_style_revisions(tmp_path):
    task = Task.create(tmp_path)
    first, second = Task.open(task.root), Task.open(task.root)
    engine.set_style(first, style())
    updated = style()
    updated['fps'] = 12
    engine.set_style(second, updated)
    entries = Task.open(task.root).entries
    assert [e['style_spec']['fps'] for e in entries] == [8, 12]


def test_concurrent_clients_preserve_each_ledger_entry(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    task = Task.create(tmp_path)
    clients = [Task.open(task.root) for _ in range(12)]
    with ThreadPoolExecutor(max_workers=12) as workers:
        list(workers.map(lambda pair: pair[1].record('client', {'number': pair[0]}),
                         enumerate(clients)))
    assert sorted(e['number'] for e in Task.open(task.root).entries) == list(range(12))


def test_export_detects_mutation_during_inspection(tmp_path, monkeypatch):
    import pytest
    from test_engine import make_minimal_glb
    task = Task.create(tmp_path / 'tasks')
    model = task.artifact('model.glb')
    make_minimal_glb(model)
    inspect = engine.inspect_glb
    def mutate(path):
        result = inspect(path)
        path.write_bytes(b'not a GLB')
        return result
    monkeypatch.setattr(engine, 'inspect_glb', mutate)
    dest = tmp_path / 'delivery'
    with pytest.raises(RuntimeError):
        engine.export(task, dest)
    assert not list(dest.glob('*.glb'))


def test_export_does_not_trust_stale_inspection(tmp_path):
    import pytest
    from test_engine import make_minimal_glb
    task = Task.create(tmp_path / 'tasks')
    model = task.artifact('model.glb')
    make_minimal_glb(model)
    engine.inspect(task)
    model.write_bytes(b'changed after inspection')
    dest = tmp_path / 'delivery'
    with pytest.raises(RuntimeError):
        engine.export(task, dest)
    assert not dest.exists()


def test_real_mcp_style_matches_core(tmp_path):
    import asyncio
    import pytest
    pytest.importorskip('mcp')
    from openfigura.mcp_server import build
    task = Task.create(tmp_path)
    async def run():
        app = build()
        result = await app.call_tool('figura_set_style',
                                     {'task_root': str(task.root), 'spec': style()})
        # MCP 2 uses snake_case; MCP 1 serializes a content/structured tuple.
        if hasattr(result, 'is_error'):
            assert not result.is_error
            return result.structured_content or json.loads(result.content[0].text)
        if hasattr(result, 'isError'):
            assert not result.isError
            return result.structuredContent or json.loads(result.content[0].text)
        return result[1]
    result = asyncio.run(run())
    assert result == engine.project_style(Task.open(task.root))
