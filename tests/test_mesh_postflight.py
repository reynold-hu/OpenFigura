from pathlib import Path
import pytest
from openfigura.core import engine, registry
from openfigura.core.task import Task, sha256_file
from test_engine import make_minimal_glb


class MeshFixture:
    id = 'blender-mesh-tools'
    def __init__(self, mode): self.mode = mode
    def capabilities(self): return registry.Capabilities(True)
    def process(self, model, output, operation, params):
        make_minimal_glb(output)
        if self.mode == 'mutate': Path(model).write_bytes(b'overwritten')
        return {'exit_code': 1 if self.mode == 'fail' else 0,
                'command': 'test-mesh-worker', 'wall_seconds': 1.25,
                'stderr_tail': 'rejected candidate' if self.mode == 'fail' else '',
                'report': {'operation': operation}}


@pytest.mark.parametrize('mode', ['mutate', 'fail'])
def test_failed_mesh_never_modifies_source_or_leaves_candidate(tmp_path, monkeypatch, mode):
    task = Task.create(tmp_path/'tasks')
    source = task.artifact('model.glb'); make_minimal_glb(source)
    digest = sha256_file(source)
    monkeypatch.setattr(registry, 'get', lambda name: MeshFixture(mode))
    with pytest.raises(RuntimeError):
        engine.mesh(task, 'optimize', {'ratio': .1})
    assert sha256_file(source) == digest
    assert not task.artifact('model-optimize.glb').exists()
    assert list((task.root/'artifacts/rejected').rglob('*.glb'))
    failed = Task.open(task.root).entries[-1]
    assert failed['command'] == 'test-mesh-worker'
    assert failed['wall_seconds'] == 1.25
    assert failed['exit_code'] == (1 if mode == 'fail' else 0)
