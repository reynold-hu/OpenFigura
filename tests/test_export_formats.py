import json
from pathlib import Path

import pytest

from openfigura.core import engine, registry
from openfigura.core.task import Task, sha256_file
from openfigura.core.registry import Capabilities
from openfigura.cli import main
from test_engine import make_minimal_glb


class FakeFormats:
    EXTENSIONS = {'fbx': 'fbx', 'obj': 'obj', 'stl': 'stl', 'usd': 'usd'}

    def __init__(self, available=True, reason='', exit_code=0, produce=True):
        self.available, self.reason, self.exit_code, self.produce = available, reason, exit_code, produce

    def capabilities(self):
        return Capabilities(self.available, reason=self.reason,
                            notes={'formats': 'glb,fbx,obj,stl,usd' if self.available else 'glb'})

    def convert(self, snapshot, converted, fmt):
        report_path = converted.with_name(converted.stem + f'.{fmt}-report.json')
        report_path.write_text(json.dumps({'format': fmt, 'warnings': ['test warning'],
                                           'visual_approval': 'pending'}))
        if self.exit_code == 0 and self.produce:
            converted.write_bytes(b'FBXBINARY')
        return {'backend': 'blender-formats', 'format': fmt, 'command': f'blender -b ... {fmt}',
                'exit_code': self.exit_code, 'wall_seconds': 1.0, 'stderr_tail': 'boom',
                'output': str(converted), 'report_path': str(report_path),
                'report': json.loads(report_path.read_text()) if self.produce else None}


def task_with_glb(tmp_path):
    task = Task.create(tmp_path / 'tasks', name='fmt')
    make_minimal_glb(task.artifact('model.glb'))
    engine.inspect(task)
    return task


def test_unsupported_format_is_rejected_early(tmp_path):
    task = task_with_glb(tmp_path)
    with pytest.raises(ValueError, match='unsupported'):
        engine.export(task, tmp_path / 'out', fmt='3mf')


def test_fbx_export_delivers_converted_glb_and_report(tmp_path, monkeypatch):
    task = task_with_glb(tmp_path)
    monkeypatch.setattr(registry, 'get', lambda name: FakeFormats())
    manifest = engine.export(task, tmp_path / 'out', fmt='fbx')
    out = tmp_path / 'out'
    assert manifest['format'] == 'fbx'
    assert (out / f'{task.id}.fbx').read_bytes() == b'FBXBINARY'
    assert manifest['converted_sha256'] == sha256_file(out / f'{task.id}.fbx')
    assert manifest['glb_sha256'] == sha256_file(out / f'{task.id}.glb')
    assert manifest['conversion_warnings'] == ['test warning']
    assert (out / 'inspect.json').is_file() and (out / 'provenance.json').is_file()
    entry = Task.open(task.root).entries[-1]
    assert entry['step'] == 'export' and entry['conversion']['exit_code'] == 0
    assert json.loads((out / 'export-manifest.json').read_text()) == manifest


def test_fbx_refuses_when_backend_unavailable(tmp_path, monkeypatch):
    task = task_with_glb(tmp_path)
    monkeypatch.setattr(registry, 'get', lambda name: FakeFormats(available=False, reason='no operators'))
    with pytest.raises(RuntimeError, match='unavailable: no operators'):
        engine.export(task, tmp_path / 'out', fmt='fbx')
    assert not (tmp_path / 'out').exists()


def test_fbx_conversion_failure_refuses_delivery(tmp_path, monkeypatch):
    task = task_with_glb(tmp_path)
    monkeypatch.setattr(registry, 'get', lambda name: FakeFormats(exit_code=1))
    with pytest.raises(RuntimeError, match='conversion fbx exited 1'):
        engine.export(task, tmp_path / 'out', fmt='fbx')
    assert not (tmp_path / 'out').exists()


def test_glb_path_never_touches_format_backend(tmp_path, monkeypatch):
    task = task_with_glb(tmp_path)
    def explode(name):
        raise AssertionError('glb export must not require the Blender format backend')
    monkeypatch.setattr(registry, 'get', explode)
    manifest = engine.export(task, tmp_path / 'out', fmt='glb')
    assert (tmp_path / 'out' / f'{task.id}.glb').is_file()


def test_cli_accepts_new_formats(tmp_path):
    import argparse
    parser = argparse.ArgumentParser()
    # mirror of the real parser's choices without spawning Blender
    from openfigura.cli import main as _m
    with pytest.raises(SystemExit):
        _m(['export', str(tmp_path), '--dest', str(tmp_path / 'x'), '--format', 'blend'])


def test_executor_export_step_passes_fmt(tmp_path, monkeypatch):
    from openfigura.core.contracts import AssetRef
    task = task_with_glb(tmp_path)
    monkeypatch.setattr(registry, 'get', lambda name: FakeFormats())
    ref = AssetRef('artifacts/model.glb', sha256_file(task.artifact('model.glb')), 'model', 'import')
    result = engine.execute(task, 'export', [ref.to_dict()], {'fmt': 'fbx'})
    assert result['status'] == 'pass'
    stage = engine.workflow_status(Task.open(task.root), result['stage_id'])
    kinds = {o['kind'] for o in stage['outputs']}
    assert 'model' in kinds
