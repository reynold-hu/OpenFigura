"""Use-case presets: resolution rules, stated bases, and frontend mirrors."""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openfigura.core import engine, registry  # noqa: E402
from openfigura.core.registry import Capabilities  # noqa: E402
from openfigura.core.task import Task  # noqa: E402


def write_glb(path: Path, index_count: int) -> None:
    gltf = {
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1,
                                                   "TEXCOORD_0": 2},
                                    "indices": 0, "material": 0, "mode": 4}]}],
        "materials": [{"pbrMetallicRoughness": {}}],
        "accessors": [{"count": index_count}, {"count": 3}, {"count": 3}],
        "buffers": [{"byteLength": 12}],
    }
    payload = json.dumps(gltf).encode()
    payload += b" " * (-len(payload) % 4)
    binchunk = b"\x00" * 12
    total = 12 + 8 + len(payload) + 8 + len(binchunk)
    path.write_bytes(struct.pack("<III", 0x46546C67, 2, total)
                     + struct.pack("<II", len(payload), 0x4E4F534A) + payload
                     + struct.pack("<II", len(binchunk), 0x004E4942) + binchunk)


class FakeMesh:
    id = 'fake-mesh'
    kind = 'mesh'

    def __init__(self):
        self.seen = None
        self.available = True

    def capabilities(self):
        return Capabilities(self.available, hardware='cpu',
                            reason='' if self.available else 'blender not found')

    def process(self, model, output, operation, params):
        self.seen = {'operation': operation, 'params': dict(params)}
        Path(output).write_bytes(b'GLB')
        report_path = Path(output).with_suffix('.mesh-report.json')
        report_path.write_text(json.dumps({'operation': operation}))
        return {'backend': self.id, 'command': 'fake mesh', 'exit_code': 0,
                'wall_seconds': 0.1, 'stdout_tail': '', 'stderr_tail': '',
                'output': str(output), 'report_path': str(report_path),
                'report': json.loads(report_path.read_text())}


def task_with_glb(tmp_path, index_count=6):
    task = Task.create(tmp_path / 'tasks', name='preset')
    write_glb(task.artifact('model.glb'), index_count)
    engine.inspect(task)
    return task


def test_presets_table_shape_and_bases():
    table = engine.presets()
    assert table['schema_version'] == 1
    assert set(table['use_cases']) == {'game', 'animation', 'print', 'vr_ar',
                                       'product_display', 'general'}
    assert table['operations'] == ['retopo', 'optimize']
    for name, preset in table['use_cases'].items():
        assert preset['basis'] in {'openfigura-recommendation', 'vendor-claim'}, name
        assert preset['note'], name


def test_retopo_use_case_fills_target_faces_when_unset(tmp_path, monkeypatch):
    task = task_with_glb(tmp_path)
    fake = FakeMesh()
    monkeypatch.setattr(registry, 'get', lambda name: fake)
    evidence = engine.mesh(task, 'retopo', use_case='game')
    assert fake.seen['params']['target_faces'] == 20_000
    assert evidence['use_case']['use_case'] == 'game'
    assert evidence['resolved_defaults']['target_faces']['value'] == 20_000
    assert evidence['resolved_defaults']['target_faces']['basis'] == 'openfigura-recommendation'
    entry = Task.open(task.root).entries[-1]
    assert entry['step'] == 'mesh' and entry['use_case']['use_case'] == 'game'
    assert entry['resolved_defaults']['target_faces']['value'] == 20_000


def test_explicit_params_beat_use_case(tmp_path, monkeypatch):
    task = task_with_glb(tmp_path)
    fake = FakeMesh()
    monkeypatch.setattr(registry, 'get', lambda name: fake)
    evidence = engine.mesh(task, 'retopo', {'target_faces': 5_000}, use_case='game')
    assert fake.seen['params']['target_faces'] == 5_000
    assert evidence['resolved_defaults'] == {}


def test_print_use_case_sets_no_implicit_budget(tmp_path, monkeypatch):
    task = task_with_glb(tmp_path)
    fake = FakeMesh()
    monkeypatch.setattr(registry, 'get', lambda name: fake)
    evidence = engine.mesh(task, 'retopo', use_case='print')
    assert fake.seen['params'].get('target_faces') is None
    assert evidence['resolved_defaults'] == {}
    assert evidence['use_case']['basis'] == 'openfigura-recommendation'


def test_optimize_use_case_computes_ratio_from_source_triangles(tmp_path, monkeypatch):
    # 60,000 indices -> 20,000 triangles; game budget 20,000 => ratio 1.0,
    # so use a lower budget case instead: source 20k tris, vr_ar target 20k is
    # still 1.0; exercise the reducing branch with a denser fixture.
    task = task_with_glb(tmp_path, index_count=90_000)   # 30,000 triangles
    fake = FakeMesh()
    monkeypatch.setattr(registry, 'get', lambda name: fake)
    evidence = engine.mesh(task, 'optimize', use_case='game')
    resolved = evidence['resolved_defaults']['ratio']
    assert resolved['source_triangles'] == 30_000
    assert resolved['target_faces'] == 20_000
    assert resolved['value'] == round(20_000 / 30_000, 6)
    assert fake.seen['params']['ratio'] == resolved['value']


def test_optimize_use_case_with_source_below_budget_is_ratio_one(tmp_path, monkeypatch):
    task = task_with_glb(tmp_path, index_count=6)        # 2 triangles
    fake = FakeMesh()
    monkeypatch.setattr(registry, 'get', lambda name: fake)
    evidence = engine.mesh(task, 'optimize', use_case='game')
    resolved = evidence['resolved_defaults']['ratio']
    assert resolved['value'] == 1.0
    assert resolved['basis'] == 'source already within the use-case budget'
    assert fake.seen['params']['ratio'] == 1.0


def test_use_case_fails_closed_for_unknown_names_and_operations(tmp_path, monkeypatch):
    task = task_with_glb(tmp_path)
    fake = FakeMesh()
    monkeypatch.setattr(registry, 'get', lambda name: fake)
    with pytest.raises(ValueError, match='unknown use case'):
        engine.mesh(task, 'retopo', use_case='cinematic')
    with pytest.raises(ValueError, match='apply to'):
        engine.mesh(task, 'uv', use_case='game')
    with pytest.raises(ValueError, match='apply to'):
        engine.mesh(task, 'segment', use_case='print')
    assert fake.seen is None
    assert not task.artifact('model-retopo.glb').exists()


def test_cli_presets_matches_engine(tmp_path, capsys):
    from openfigura.cli import main
    assert main(['presets']) == 0
    assert json.loads(capsys.readouterr().out) == engine.presets()


def test_cli_mesh_use_case_rejects_unknown_name():
    from openfigura.cli import main
    with pytest.raises(SystemExit):
        main(['mesh', 'x', '--operation', 'retopo', '--use-case', 'cinematic'])


def test_mcp_presets_and_mesh_use_case_mirror_engine(tmp_path, monkeypatch):
    import asyncio
    pytest.importorskip('mcp')
    from openfigura.mcp_server import build
    task = task_with_glb(tmp_path)
    fake = FakeMesh()
    monkeypatch.setattr(registry, 'get', lambda name: fake)

    async def run():
        app = build()
        presets_result = await app.call_tool('figura_presets', {})
        mesh_result = await app.call_tool('figura_mesh', {
            'task_root': str(task.root), 'operation': 'retopo',
            'params': None, 'use_case': 'animation'})

        def unwrap(result):
            if hasattr(result, 'content'):
                return json.loads(result.content[0].text)
            return result[1]
        return unwrap(presets_result), unwrap(mesh_result)

    table, evidence = asyncio.run(run())
    assert table == engine.presets()
    assert evidence['resolved_defaults']['target_faces']['value'] == 50_000
    assert evidence['use_case']['basis'] == 'vendor-claim'
