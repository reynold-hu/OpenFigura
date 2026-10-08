import pytest

from openfigura.core import engine
from openfigura.core.task import Task
from test_unimate import rigged_task, wire, FakeUnimate, FakeGate, _rig_refs
from test_rig_transfer import skinned_static_glb


@pytest.mark.parametrize('value', ['false', 'true', 1, None])
def test_nc_acceptance_requires_literal_boolean(tmp_path, monkeypatch, value):
    task = rigged_task(tmp_path)
    wire(monkeypatch, ['clip.glb'], ['pass'])
    with pytest.raises(ValueError, match='boolean'):
        engine.animate(task, 'walk', accept_nc_license=value)
    assert not task.artifact('model-motion.glb').exists()


def test_execute_cannot_coerce_nc_string(tmp_path, monkeypatch):
    task, refs = _rig_refs(tmp_path)
    wire(monkeypatch, ['clip.glb'], ['pass'])
    with pytest.raises(ValueError):
        engine.execute(task, 'animate', refs, {'prompt': 'walk', 'accept_nc_license': 'false'})
    assert not any(p.name == 'model-motion.glb' for p in task.root.rglob('*.glb'))


def test_late_gate_failure_does_not_leave_accepted_candidate(tmp_path, monkeypatch):
    task = rigged_task(tmp_path)
    generator, _ = wire(monkeypatch, ['clip-a.glb', 'clip-b.glb'], ['pass', 'pass'])
    class Crashing(FakeGate):
        def gate(self, *args, **kwargs):
            if self.n == 1:
                raise RuntimeError('gate crash')
            return super().gate(*args, **kwargs)
    gate = Crashing(['pass'])
    monkeypatch.setattr('openfigura.core.registry.get',
                        lambda name: gate if name == 'blender-motion-gate' else generator)
    with pytest.raises(RuntimeError, match='crash'):
        engine.animate(task, 'walk', accept_nc_license=True)
    assert not task.artifact('model-motion.glb').exists()


def test_animate_rejects_modified_original(tmp_path, monkeypatch):
    task = rigged_task(tmp_path)
    class Mutates(FakeUnimate):
        def generate_motion(self, model, *args, **kwargs):
            result = super().generate_motion(model, *args, **kwargs)
            model.write_bytes(b'modified input')
            return result
    generator = Mutates(['clip.glb'])
    monkeypatch.setattr('openfigura.core.registry.get',
                        lambda name: FakeGate(['pass']) if name == 'blender-motion-gate' else generator)
    with pytest.raises(RuntimeError, match='modified'):
        engine.animate(task, 'walk', accept_nc_license=True)
    assert not task.artifact('model-motion.glb').exists()


def test_transfer_rejects_unweighted_and_quarantines(tmp_path, monkeypatch):
    from test_rig_transfer import _wire_engine
    from openfigura.core import registry
    task = _wire_engine(tmp_path, monkeypatch)
    backend = registry.get('blender-rig-transfer')
    transfer = backend.transfer
    def bad(*args, **kwargs):
        result = transfer(*args, **kwargs)
        result['report']['vertices_without_weights'] = 3
        return result
    backend.transfer = bad
    monkeypatch.setattr(registry, 'get', lambda name: backend)
    with pytest.raises(RuntimeError, match='unweighted'):
        engine.transfer_rig(task, 'model-autorig.glb')
    assert not task.artifact('model-transferred.glb').exists()


def test_execute_annotation_must_be_declared_and_hashed(tmp_path, monkeypatch):
    task, refs = _rig_refs(tmp_path)
    annotation = tmp_path / 'annotation.json'
    annotation.write_text('{}')
    wire(monkeypatch, ['clip.glb'], ['pass'])
    with pytest.raises(ValueError, match='declared'):
        engine.execute(task, 'animate', refs, {'prompt': 'walk',
            'accept_nc_license': True, 'annotation': str(annotation)})


def test_motion_annotation_is_a_private_snapshot(tmp_path, monkeypatch):
    task = rigged_task(tmp_path)
    annotation = tmp_path / 'annotation.json'
    annotation.write_text('{}')
    class MutatesAnnotation(FakeUnimate):
        def generate_motion(self, model, *args, **kwargs):
            from pathlib import Path
            Path(args[-1]).write_text('changed')
            return super().generate_motion(model, *args, **kwargs)
    generator = MutatesAnnotation(['clip.glb'])
    monkeypatch.setattr('openfigura.core.registry.get',
        lambda name: FakeGate(['pass']) if name == 'blender-motion-gate' else generator)
    with pytest.raises(RuntimeError, match='annotation'):
        engine.animate(task, 'walk', accept_nc_license=True, annotation=str(annotation))
    assert annotation.read_text() == '{}'
