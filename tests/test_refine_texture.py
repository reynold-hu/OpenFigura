"""Core contract tests run without optional image dependencies or model installs."""
import json
from pathlib import Path
import pytest
from openfigura.core import engine, registry
from openfigura.core.task import Task
from openfigura.core.registry import Capabilities
from test_engine import make_minimal_glb

class Painter:
    def capabilities(self):return Capabilities(True,hardware='cpu')
    def refine(self, model, views, output, mask=None, strength=1.0):
        make_minimal_glb(output)
        return {'exit_code':0,'produced':True,'command':'fake painter','wall_seconds':0,'geometry_unchanged':True}

@pytest.fixture
def setup(tmp_path, monkeypatch):
    task=Task.create(tmp_path/'tasks',name='refine');make_minimal_glb(task.artifact('model.glb'))
    views=tmp_path/'views';views.mkdir();(views/'front.png').write_bytes(b'fixture')
    (views/'transforms.json').write_text(json.dumps({'camera_angle_x':.349,'mesh_scale':1,'frames':[{'file_path':'front.png','transform_matrix':[[1,0,0,0],[0,0,-1,-3],[0,1,0,0],[0,0,0,1]]}]}))
    monkeypatch.setattr(registry,'get',lambda bid:Painter())
    return task,views

def test_refine_preserves_original_and_records_replayable_inputs(setup):
    task,views=setup;original=task.artifact('model.glb').read_bytes()
    result=engine.refine_texture(task,views)
    assert result['status']=='pass' and result['output_sha256']
    assert task.artifact('model.glb').read_bytes()==original
    assert task.artifact('model-refined.glb').exists()
    entries=Task.open(task.root).entries;entry=entries[-1]
    assert entry['step']=='refine_texture' and entry['reference_hashes']['front.png']
    assert (task.root/entry['views_dir']/'front.png').exists()

def test_refine_refuses_reference_path_escape(setup):
    task,views=setup;meta=json.loads((views/'transforms.json').read_text());meta['frames'][0]['file_path']='../outside.png';(views/'transforms.json').write_text(json.dumps(meta))
    with pytest.raises(ValueError,match='reference'):engine.refine_texture(task,views)
    assert not task.artifact('model-refined.glb').exists()

def test_refine_refuses_output_overwrite(setup):
    task,views=setup;task.artifact('model-refined.glb').write_bytes(b'preserve')
    with pytest.raises(FileExistsError):engine.refine_texture(task,views)
    assert task.artifact('model-refined.glb').read_bytes()==b'preserve'

def test_refine_records_backend_failure(setup,monkeypatch):
    task,views=setup
    class Bad(Painter):
        def refine(self,*a,**kw):return {'exit_code':1,'produced':False}
    monkeypatch.setattr(registry,'get',lambda bid:Bad())
    with pytest.raises(RuntimeError):engine.refine_texture(task,views)
    assert Task.open(task.root).entries[-1]['status']=='fail'

def test_refine_rejects_invalid_strength(setup):
    task,views=setup
    with pytest.raises(ValueError):engine.refine_texture(task,views,strength=float('nan'))

def test_refined_candidate_can_be_inspected_and_exported_separately(setup,tmp_path):
    task,views=setup;engine.refine_texture(task,views)
    report=engine.inspect(task,artifact='model-refined.glb')
    assert report['ok']
    out=tmp_path/'delivery';manifest=engine.export(task,out,artifact='model-refined.glb')
    assert (out/'refine-model-refined.glb').exists()
    assert manifest['artifact']=='model-refined.glb'
    assert task.artifact('model.glb').exists()

def test_candidate_artifact_cannot_escape_task(setup):
    task,views=setup
    with pytest.raises(ValueError):engine.inspect(task,artifact='../model.glb')

def test_failed_refinement_retains_exit_code(setup,monkeypatch):
    task,views=setup
    class Bad(Painter):
        def refine(self,*a,**kw):return {'exit_code':17,'produced':False,'stderr_tail':'fixture failure'}
    monkeypatch.setattr(registry,'get',lambda bid:Bad())
    with pytest.raises(RuntimeError):engine.refine_texture(task,views)
    assert Task.open(task.root).entries[-1]['exit_code']==17

def test_generate_records_existing_raw_geometry_and_camera_evidence(setup,monkeypatch):
    task,_=setup
    class Generator(Painter):
        def generate(self, image, output, params):
            make_minimal_glb(output)
            output.with_suffix('.ply').write_bytes(b'raw geometry')
            views=output.with_suffix('.svviews');views.mkdir();(views/'transforms.json').write_text('{}')
            return {'produced':True,'exit_code':0}
    monkeypatch.setattr(registry,'get',lambda bid:Generator())
    from test_engine import _png_bytes
    (task.root/'input/ref.png').write_bytes(_png_bytes())
    result=engine.generate(task,'fixture')
    assert result['intermediate_hashes']['model.ply']
    assert result['intermediate_hashes']['model.svviews/transforms.json']
