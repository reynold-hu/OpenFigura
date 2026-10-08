"""Neural rig tool boundary tests; no model dependency in the core."""
import json
from pathlib import Path
import pytest
from openfigura.core import engine,registry
from openfigura.core.task import Task
from openfigura.core.registry import Capabilities
from test_engine import make_minimal_glb
from test_rig import skinned_glb

class FakeNeural:
    def capabilities(self):return Capabilities(True,hardware='cpu')
    def autorig(self,model,output,**options):
        skinned_glb(output)
        return {'produced':True,'manual_coordinates':False,'fit_validation':{'status':'pass'},'device':options['device'],'seed':options['seed'],'exit_code':0}

@pytest.fixture
def fixture(tmp_path,monkeypatch):
    task=Task.create(tmp_path/'tasks',name='auto');make_minimal_glb(task.artifact('model.glb'))
    monkeypatch.setattr(registry,'get',lambda name:FakeNeural())
    return task

def test_neural_rig_preserves_source_and_records_options(fixture):
    before=fixture.artifact('model.glb').read_bytes()
    result=engine.autorig(fixture,device='cpu',seed=42,query_chunk=8192)
    assert result['status']=='pass' and result['manual_coordinates'] is False
    assert result['seed']==42 and result['query_chunk']==8192
    assert fixture.artifact('model.glb').read_bytes()==before
    assert fixture.artifact('model-autorig.glb').is_file()

def test_unavailable_neural_rig_does_not_fallback(fixture,monkeypatch):
    class Missing(FakeNeural):
        def capabilities(self):return Capabilities(False,reason='torch_cluster missing')
    monkeypatch.setattr(registry,'get',lambda name:Missing())
    with pytest.raises(RuntimeError,match='torch_cluster'):engine.autorig(fixture)
    assert not fixture.artifact('model-autorig.glb').exists()

def test_invalid_device_and_chunk_are_rejected(fixture):
    for kw in [{'device':'mps'}, {'query_chunk':0},{'query_chunk':65537},{'seed':-1}]:
        with pytest.raises(ValueError):engine.autorig(fixture,**kw)

def test_neural_binding_refuses_existing_skin(fixture):
    skinned_glb(fixture.artifact('model.glb'))
    with pytest.raises(ValueError,match='already'):engine.autorig(fixture)

def test_neural_binding_refuses_overwrite(fixture):
    fixture.artifact('model-autorig.glb').write_bytes(b'preserve')
    with pytest.raises(FileExistsError):engine.autorig(fixture)

def test_runtime_failure_is_recorded_without_manual_substitution(fixture,monkeypatch):
    class Broken(FakeNeural):
        def autorig(self,*args,**kwargs):return {'produced':False,'exit_code':1,'stderr_tail':'neural output nonfinite'}
    monkeypatch.setattr(registry,'get',lambda name:Broken())
    with pytest.raises(RuntimeError,match='nonfinite'):engine.autorig(fixture)
    assert Task.open(fixture.root).entries[-1]['status']=='fail'

def test_rejected_neural_candidate_is_preserved_but_not_exportable(fixture,monkeypatch,tmp_path):
    class Invalid(FakeNeural):
        def autorig(self,model,output,**options):
            result=super().autorig(model,output,**options)
            output.with_suffix('.blend').write_bytes(b'diagnostic')
            result['fit_validation']={'status':'fail'}
            return result
    monkeypatch.setattr(registry,'get',lambda name:Invalid())
    with pytest.raises(RuntimeError,match='continuity'):engine.autorig(fixture)
    assert not fixture.artifact('model-autorig.glb').exists()
    record=Task.open(fixture.root).entries[-1]
    assert len(record['rejected_artifacts'])==2
    assert all((fixture.root/p).is_file() for p in record['rejected_artifacts'])
    with pytest.raises(FileNotFoundError):engine.export(fixture,tmp_path/'delivery',artifact='model-autorig.glb')
