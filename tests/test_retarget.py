import pytest
from pathlib import Path
from openfigura.core import engine,registry
from openfigura.core.task import Task
from openfigura.core.registry import Capabilities
from test_rig import skinned_glb

class FakeMotion:
    def capabilities(self):return Capabilities(True,hardware='cpu')
    def retarget(self,model,animation,output,frames,fps):
        skinned_glb(output)
        return {'produced':True,'exit_code':0,'manual_keyframes':False,'contact_validation':{'status':'pass'}}

@pytest.fixture
def fixture(tmp_path,monkeypatch):
    task=Task.create(tmp_path/'tasks',name='motion');skinned_glb(task.artifact('model-autorig.glb'))
    source=tmp_path/'clip.glb';skinned_glb(source)
    monkeypatch.setattr(registry,'get',lambda name:FakeMotion())
    return task,source

def test_retarget_preserves_inputs_and_requires_checked_animation(fixture):
    task,source=fixture;original=task.artifact('model-autorig.glb').read_bytes();clip=source.read_bytes()
    result=engine.retarget(task,source,frames=31,fps=24)
    assert result['status']=='pass' and result['manual_keyframes'] is False
    assert task.artifact('model-autorig.glb').read_bytes()==original and source.read_bytes()==clip
    assert task.artifact('model-animated.glb').exists()

def test_retarget_cannot_accept_unchecked_contact(fixture,monkeypatch):
    task,source=fixture
    class Unchecked(FakeMotion):
        def retarget(self,*args,**kwargs):
            result=super().retarget(*args,**kwargs);result['contact_validation']={'status':'fail'};return result
    monkeypatch.setattr(registry,'get',lambda name:Unchecked())
    with pytest.raises(RuntimeError,match='contact'):engine.retarget(task,source)
    assert Task.open(task.root).entries[-1]['status']=='fail'

def test_retarget_bounds_work_and_refuses_overwrite(fixture):
    task,source=fixture
    for kw in [{'frames':0},{'frames':241},{'fps':0},{'fps':121}]:
        with pytest.raises(ValueError):engine.retarget(task,source,**kw)
    task.artifact('model-animated.glb').write_bytes(b'preserve')
    with pytest.raises(FileExistsError):engine.retarget(task,source)

def test_animation_source_does_not_need_render_materials(fixture):
    import json,struct
    from test_engine import make_minimal_glb_from
    task,source=fixture;data=source.read_bytes();doc=json.loads(data[20:20+struct.unpack_from('<I',data,12)[0]])
    doc.pop('materials',None)
    for mesh in doc['meshes']:
        for p in mesh['primitives']:p.pop('material',None)
    make_minimal_glb_from(source,doc)
    assert engine.retarget(task,source)['status']=='pass'

def test_retarget_refuses_unvalidated_extra_clips(fixture,monkeypatch):
    import json,struct
    from test_engine import make_minimal_glb_from
    task,source=fixture
    class Extra(FakeMotion):
        def retarget(self,model,animation,output,frames,fps):
            result=super().retarget(model,animation,output,frames,fps)
            data=output.read_bytes();doc=json.loads(data[20:20+struct.unpack_from('<I',data,12)[0]])
            doc['animations'].append({'name':'UncheckedRaw','channels':[]})
            make_minimal_glb_from(output,doc);return result
    monkeypatch.setattr(registry,'get',lambda name:Extra())
    with pytest.raises(RuntimeError,match='one'):engine.retarget(task,source)

def test_rejected_motion_candidate_is_quarantined(fixture,monkeypatch,tmp_path):
    task,source=fixture
    class Invalid(FakeMotion):
        def retarget(self,*args,**kwargs):
            result=super().retarget(*args,**kwargs)
            result['contact_validation']={'status':'fail'}
            return result
    monkeypatch.setattr(registry,'get',lambda name:Invalid())
    with pytest.raises(RuntimeError,match='contact'):engine.retarget(task,source)
    assert not task.artifact('model-animated.glb').exists()
    record=Task.open(task.root).entries[-1]
    assert len(record['rejected_artifacts'])==1
    assert (task.root/record['rejected_artifacts'][0]).is_file()
    with pytest.raises(FileNotFoundError):engine.export(task,tmp_path/'delivery',artifact='model-animated.glb')
