import json
from pathlib import Path

import pytest

from openfigura.core import engine
from openfigura.core.contracts import AssetRef
from openfigura.core.task import Task, sha256_file
from openfigura.core.workflow import Workflow
from test_engine import make_minimal_glb


def imported(tmp_path):
    task = Task.create(tmp_path / 'tasks')
    path = task.artifact('model.glb')
    make_minimal_glb(path)
    ref = AssetRef('artifacts/model.glb', sha256_file(path), 'model', 'import')
    return task, ref


def test_execute_inspect_real_engine_in_separate_stage(tmp_path):
    task, ref = imported(tmp_path)
    result = engine.execute(task, 'inspect', [ref.to_dict()], {})
    assert result['status'] == 'pass'
    stage = Workflow(task.root).status(result['stage_id'])
    assert stage['status'] == 'pass'
    report = next(AssetRef.from_dict(r) for r in stage['outputs'] if r['kind'] == 'report')
    assert json.loads(report.verify(task.root).read_text())['ok']
    assert ref.verify(task.root).exists()


def test_execute_cache_reuses_verified_report(tmp_path, monkeypatch):
    task, ref = imported(tmp_path)
    first = engine.execute(task, 'inspect', [ref.to_dict()], {})
    # Counting backend execution is legitimate here; actual inspector ran first.
    calls = []
    inspect = engine.inspect
    def spy(*args, **kwargs):
        calls.append(1)
        return inspect(*args, **kwargs)
    monkeypatch.setattr(engine, 'inspect', spy)
    second = engine.execute(task, 'inspect', [ref.to_dict()], {})
    assert second['cached_from'] == first['stage_id']
    assert calls == []


def test_execute_invalid_glb_records_failure_and_preserves_input(tmp_path):
    task, ref = imported(tmp_path)
    model = task.artifact('model.glb')
    model.write_bytes(b'invalid')
    ref = AssetRef('artifacts/model.glb', sha256_file(model), 'model', 'import')
    with pytest.raises(ValueError):
        engine.execute(task, 'inspect', [ref.to_dict()], {})
    assert Workflow(task.root).status()['stages'][-1]['status'] == 'fail'
    assert model.read_bytes() == b'invalid'


def test_execute_rejects_unknown_operation_before_any_stage(tmp_path):
    task, ref = imported(tmp_path)
    with pytest.raises(ValueError):
        engine.execute(task, 'eval', [ref.to_dict()], {})
    assert not (task.root / 'stages').exists()


def test_execute_refuses_invalid_input_hash(tmp_path):
    task, ref = imported(tmp_path)
    bad = ref.to_dict()
    bad['sha256'] = '0' * 64
    with pytest.raises(ValueError):
        engine.execute(task, 'inspect', [bad], {})
    assert not (task.root / 'stages').exists()


def test_execute_invalid_params_cannot_pass(tmp_path):
    task, ref = imported(tmp_path)
    with pytest.raises((ValueError, TypeError)):
        engine.execute(task, 'inspect', [ref.to_dict()], {'unexpected': True})


def test_execute_does_not_copy_undeclared_models(tmp_path):
    task, ref = imported(tmp_path)
    alternate = task.artifact('other.glb')
    make_minimal_glb(alternate)
    result = engine.execute(task, 'inspect', [ref.to_dict()], {})
    stage_dir = task.root / 'stages' / result['stage_id']
    assert not (stage_dir / 'artifacts' / 'other.glb').exists()
