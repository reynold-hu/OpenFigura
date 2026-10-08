"""Persistent workflow transitions and task-local verified cache behavior."""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from openfigura.core.contracts import AssetRef
from openfigura.core.task import Task, sha256_file
import importlib.util


def test_workflow_api_exists():
    assert importlib.util.find_spec("openfigura.core.workflow") is not None


try:
    from openfigura.core.workflow import Workflow
except ModuleNotFoundError:
    Workflow = None


@pytest.fixture
def task(tmp_path):
    return Task.create(tmp_path, 'work')


def ref(task, path, producer='input', content=b'asset'):
    target = task.root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return AssetRef(path, sha256_file(target), 'mesh', producer)


def submit(workflow, inputs=None, params=None):
    return workflow.submit('generate', inputs or [], params or {}, 'fake', '1')


def test_persistent_success_and_events_are_copies(task):
    workflow = Workflow(task.root)
    stage = submit(workflow, [ref(task, 'input/a')])
    assert stage['status'] == 'queued'
    workflow.claim(stage['stage_id'])
    output = ref(task, 'artifacts/result', 'generate')
    assert workflow.complete(stage['stage_id'], [output])['status'] == 'pass'
    reopened = Workflow(task.root)
    assert reopened.status(stage['stage_id'])['outputs'] == [output.to_dict()]
    events = reopened.events(stage['stage_id'])
    assert [event['status'] for event in events] == ['queued', 'running', 'pass']
    events[0]['status'] = 'broken'
    assert reopened.events(stage['stage_id'])[0]['status'] == 'queued'
    assert len(reopened.status()['stages']) == 1


def test_two_instances_only_one_can_claim(task):
    first, second = Workflow(task.root), Workflow(task.root)
    stage = submit(first)
    barrier = Barrier(2)
    def claim(workflow):
        barrier.wait()
        try:
            workflow.claim(stage['stage_id'])
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(claim, [first, second])) == [False, True]
    assert len(first.events(stage['stage_id'])) == 2


def test_invalid_transitions_preserve_history(task):
    workflow = Workflow(task.root)
    stage = submit(workflow)
    sid = stage['stage_id']
    with pytest.raises(ValueError):
        workflow.complete(sid, [])
    workflow.claim(sid)
    before = workflow.events(sid)
    for operation in (lambda: workflow.claim(sid), lambda: workflow.cancel(sid),
                      lambda: workflow.resume(sid)):
        with pytest.raises(ValueError):
            operation()
        assert workflow.events(sid) == before
    workflow.fail(sid, 'backend unavailable')
    retry = workflow.resume(sid)
    assert retry['stage_id'] != sid
    assert retry['attempt'] == 2
    assert retry['resumed_from'] == sid
    assert workflow.status(sid)['status'] == 'fail'
    assert workflow.cancel(retry['stage_id'])['status'] == 'cancelled'
    assert workflow.resume(retry['stage_id'])['attempt'] == 3
    with pytest.raises(ValueError):
        workflow.status('missing')


def test_claim_rechecks_inputs_without_transition(task):
    workflow = Workflow(task.root)
    asset = ref(task, 'input/a')
    stage = submit(workflow, [asset])
    (task.root / asset.task_relative_path).write_bytes(b'changed')
    with pytest.raises(ValueError):
        workflow.claim(stage['stage_id'])
    assert workflow.status(stage['stage_id'])['status'] == 'queued'
    assert len(workflow.events(stage['stage_id'])) == 1


def test_complete_requires_new_verified_matching_output(task):
    workflow = Workflow(task.root)
    asset = ref(task, 'input/a', 'generate')
    stage = submit(workflow, [asset])
    sid = stage['stage_id']
    workflow.claim(sid)
    for output in (asset, ref(task, 'artifacts/rejected/a', 'generate'),
                   ref(task, 'artifacts/wrong', 'other')):
        with pytest.raises(ValueError):
            workflow.complete(sid, [output])
    assert len(workflow.events(sid)) == 2
    output = ref(task, 'artifacts/output', 'generate')
    (task.root / output.task_relative_path).write_bytes(b'changed')
    with pytest.raises(ValueError):
        workflow.complete(sid, [output])


def test_cache_is_canonical_and_verifies_actual_bytes(task):
    workflow = Workflow(task.root)
    asset = ref(task, 'input/a')
    stage = submit(workflow, [asset], {'b': 2, 'a': [True, None]})
    workflow.claim(stage['stage_id'])
    output = ref(task, 'artifacts/output', 'generate')
    workflow.complete(stage['stage_id'], [output])
    hit = submit(workflow, [asset], {'a': [True, None], 'b': 2})
    assert hit['status'] == 'pass'
    assert hit['cached_from'] == stage['stage_id']
    assert hit['cache_key'] == stage['cache_key']
    (task.root / output.task_relative_path).write_bytes(b'changed')
    assert submit(workflow, [asset], {'b': 2, 'a': [True, None]})['status'] == 'queued'
    (task.root / asset.task_relative_path).write_bytes(b'changed')
    with pytest.raises(ValueError):
        submit(workflow, [asset])


@pytest.mark.parametrize('params', [{'x': float('nan')}, {1: 'bad'}, {'x': (1, 2)}, {'x': object()}])
def test_strict_params_rejected_before_mutation(task, params):
    workflow = Workflow(task.root)
    with pytest.raises((ValueError, TypeError)):
        workflow.submit('generate', [], params, 'fake', '1')
    assert workflow.status()['stages'] == []


@pytest.mark.parametrize('args', [('', [], {}, 'fake', '1'), ('s', [], [], 'fake', '1'),
                                  ('s', [], {}, '', '1'), ('s', [], {}, 'fake', '')])
def test_invalid_submit_metadata(task, args):
    workflow = Workflow(task.root)
    with pytest.raises((ValueError, TypeError)):
        workflow.submit(*args)
    assert workflow.status()['stages'] == []


def test_task_and_schema_must_exist_and_match(task, tmp_path):
    with pytest.raises((ValueError, FileNotFoundError)):
        Workflow(tmp_path / 'missing')
    Workflow(task.root)
    with sqlite3.connect(task.root / 'workflow.sqlite3') as database:
        database.execute('PRAGMA user_version = 99')
    with pytest.raises(ValueError, match='schema'):
        Workflow(task.root)


def test_complete_reverifies_inputs_and_requires_outputs(task):
    workflow = Workflow(task.root)
    asset = ref(task, 'input/a')
    stage = submit(workflow, [asset])
    sid = stage['stage_id']
    workflow.claim(sid)
    output = ref(task, 'artifacts/output', 'generate')
    with pytest.raises(ValueError):
        workflow.complete(sid, [])
    (task.root / asset.task_relative_path).write_bytes(b'corrupt')
    with pytest.raises(ValueError):
        workflow.complete(sid, [output])
    assert workflow.status(sid)['status'] == 'running'
    assert len(workflow.events(sid)) == 2


def test_complete_rejects_hardlink_alias_of_input(task):
    workflow = Workflow(task.root)
    asset = ref(task, 'input/a', 'generate')
    stage = submit(workflow, [asset])
    workflow.claim(stage['stage_id'])
    alias = task.root / 'artifacts/alias'
    alias.hardlink_to(task.root / asset.task_relative_path)
    output = AssetRef('artifacts/alias', asset.sha256, 'mesh', 'generate')
    with pytest.raises(ValueError):
        workflow.complete(stage['stage_id'], [output])


@pytest.mark.parametrize('replacement', ['hardlink', 'rejected_symlink', 'producer'])
def test_cache_reapplies_output_acceptance_guards(task, replacement):
    workflow = Workflow(task.root)
    asset = ref(task, 'input/a')
    stage = submit(workflow, [asset])
    sid = stage['stage_id']
    workflow.claim(sid)
    output = ref(task, 'artifacts/output', 'generate')
    workflow.complete(sid, [output])
    path = task.root / output.task_relative_path
    if replacement == 'hardlink':
        path.unlink()
        path.hardlink_to(task.root / asset.task_relative_path)
    elif replacement == 'rejected_symlink':
        rejected = ref(task, 'artifacts/rejected/candidate', 'generate')
        path.unlink()
        path.symlink_to(task.root / rejected.task_relative_path)
    else:
        with sqlite3.connect(workflow.database) as database:
            payload = json.loads(database.execute(
                'SELECT payload FROM stages WHERE stage_id = ?', (sid,)).fetchone()[0])
            payload['outputs'][0]['producer_step'] = 'other'
            database.execute('UPDATE stages SET payload = ? WHERE stage_id = ?',
                             (json.dumps(payload), sid))
    before = workflow.events(sid)
    fresh = submit(workflow, [asset])
    assert fresh['status'] == 'queued'
    assert fresh['cached_from'] is None
    assert workflow.events(sid) == before
