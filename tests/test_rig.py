"""Calibrated rig contract tests, without Blender or optional image libraries."""
import json
from pathlib import Path
import pytest
from openfigura.core import engine,registry
from openfigura.core.task import Task
from openfigura.core.inspect import inspect_glb
from openfigura.core.registry import Capabilities
from test_engine import make_minimal_glb,make_minimal_glb_from

def skinned_glb(path):
    make_minimal_glb(path)
    import struct
    data=path.read_bytes();doc=json.loads(data[20:20+struct.unpack_from('<I',data,12)[0]])
    doc['meshes'][0]['primitives'][0]['attributes'].update(JOINTS_0=3,WEIGHTS_0=4)
    doc['skins']=[{'joints':[1]}];doc['nodes']=[{'mesh':0,'skin':0},{'name':'Bone'}]
    doc['animations']=[{'name':'TestGesture','channels':[]}]
    make_minimal_glb_from(path,doc)

class FakeRig:
    def capabilities(self):return Capabilities(True,hardware='cpu')
    def rig(self,model,calibration,output,skin_method):
        skinned_glb(output)
        return {'produced':True,'exit_code':0,'skin_method':skin_method,'wall_seconds':0}

@pytest.fixture
def fixture(tmp_path,monkeypatch):
    task=Task.create(tmp_path/'tasks',name='rig');make_minimal_glb(task.artifact('model.glb'))
    calib=tmp_path/'calibration.json';calib.write_text(json.dumps({'bones':{'spine':{'head':[0,0,0],'tail':[0,0,1]}}}))
    monkeypatch.setattr(registry,'get',lambda bid:FakeRig())
    return task,calib

def test_inspection_reports_skin_and_animation(tmp_path):
    path=tmp_path/'skin.glb';skinned_glb(path);report=inspect_glb(path)
    assert report['has_skinning'] and report['joint_count']==1
    assert report['animation_clips']==['TestGesture']

def test_rig_preserves_source_and_records_calibration(fixture):
    task,calib=fixture;original=task.artifact('model.glb').read_bytes()
    result=engine.rig(task,calib,skin_method='capsule')
    assert result['status']=='pass' and result['calibration_sha256']
    assert result['skin_method']=='capsule' and task.artifact('model.glb').read_bytes()==original
    assert task.artifact('model-rigged.glb').exists()

def test_rig_does_not_silently_fallback(fixture,monkeypatch):
    task,calib=fixture
    class Fail(FakeRig):
        def rig(self,*args,**kwargs):return {'produced':False,'exit_code':1,'stderr_tail':'Bone Heat failed'}
    monkeypatch.setattr(registry,'get',lambda bid:Fail())
    with pytest.raises(RuntimeError):engine.rig(task,calib)
    assert Task.open(task.root).entries[-1]['status']=='fail'
    assert not task.artifact('model-rigged.glb').exists()

def test_rig_rejects_nonfinite_bone(fixture):
    task,calib=fixture;calib.write_text('{"bones":{"spine":{"head":[0,0,NaN],"tail":[0,0,1]}}}')
    with pytest.raises(ValueError):engine.rig(task,calib)

def test_rig_refuses_candidate_overwrite(fixture):
    task,calib=fixture;task.artifact('model-rigged.glb').write_bytes(b'preserve')
    with pytest.raises(FileExistsError):engine.rig(task,calib)

def test_pose_frame_is_forwarded_to_renderer(fixture,monkeypatch):
    task,_=fixture;skinned_glb(task.artifact('model-rigged.glb'));seen={}
    class Renderer:
        def capabilities(self):return Capabilities(True)
        def render_views(self,glb,out,**params):
            seen.update(params);seen['out']=out
            out.mkdir(parents=True,exist_ok=True);(out/'front.png').write_bytes(b'frame')
            return {'exit_code':0,'frames':['front.png']}
    monkeypatch.setattr(registry,'get',lambda bid:Renderer())
    engine.render(task,artifact='model-rigged.glb',frame=15)
    assert seen['frame']==15 and seen['out'].name=='frame-15'

def test_invalid_pose_frame_is_rejected(fixture):
    task,_=fixture
    with pytest.raises(ValueError):engine.render(task,frame=-1)

def test_rig_refuses_rebinding_an_existing_skin(fixture):
    task,calib=fixture;skinned_glb(task.artifact('model.glb'))
    with pytest.raises(ValueError,match='already'):engine.rig(task,calib)

def test_calibration_fixture_cannot_be_applied_to_wrong_model(fixture):
    task,calib=fixture;data=json.loads(calib.read_text());data['model_sha256']='0'*64;calib.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='calibration'):engine.rig(task,calib)

def test_rig_refuses_structurally_broken_output(fixture,monkeypatch):
    task,calib=fixture
    class Broken(FakeRig):
        def rig(self,model,calibration,output,skin_method):
            skinned_glb(output)
            import struct
            raw=output.read_bytes();doc=json.loads(raw[20:20+struct.unpack_from('<I',raw,12)[0]])
            doc['meshes'][0]['primitives'][0]['attributes'].pop('NORMAL')
            make_minimal_glb_from(output,doc)
            return {'produced':True,'exit_code':0}
    monkeypatch.setattr(registry,'get',lambda bid:Broken())
    with pytest.raises(RuntimeError):engine.rig(task,calib)
    assert Task.open(task.root).entries[-1]['status']=='fail'
