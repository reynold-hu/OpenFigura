import json
import pytest
from openfigura.core import engine, registry
from openfigura.core.task import Task, sha256_file
from openfigura.core.contracts import AssetRef
from test_engine import make_minimal_glb

class FakePivot:
    id='gltf-pivot'
    def capabilities(self):return registry.Capabilities(True,hardware='cpu')
    def pivot(self,model,output,mode):
        make_minimal_glb(output)
        digest=sha256_file(output)
        report={'attribute_bytes_preserved':True,'mode':mode,'output_sha256':digest}
        rp=output.with_suffix('.pivot-report.json');rp.write_text(json.dumps(report))
        owned={str(p.absolute()):[p.stat().st_dev,p.stat().st_ino] for p in (output,rp)}
        return {'status':'pass','exit_code':0,'produced':True,'report':report,'report_path':str(rp),'wall_seconds':.01,'owned_artifacts':owned,'output_sha256':digest,'report_sha256':sha256_file(rp)}

def task(tmp_path,monkeypatch):
    t=Task.create(tmp_path/'tasks');make_minimal_glb(t.artifact('model.glb'))
    monkeypatch.setattr(registry,'get',lambda name:FakePivot())
    return t

def test_pivot_engine_and_execute_emit_verified_model_report(tmp_path,monkeypatch):
    t=task(tmp_path,monkeypatch);digest=sha256_file(t.artifact('model.glb'))
    ref=AssetRef('artifacts/model.glb',digest,'model','import').to_dict()
    result=engine.execute(t,'pivot',[ref],{'mode':'ground'})
    assert result['status']=='pass' and result['backend']=='gltf-pivot'
    assert {a['kind'] for a in result['outputs']}=={'model','report'}
    assert sha256_file(t.artifact('model.glb'))==digest

def test_pivot_source_snapshot_and_failure_quarantine(tmp_path,monkeypatch):
    t=task(tmp_path,monkeypatch);digest=sha256_file(t.artifact('model.glb'))
    class Bad(FakePivot):
        def pivot(self,model,output,mode):
            result=super().pivot(model,output,mode);model.write_bytes(b'changed');return result
    monkeypatch.setattr(registry,'get',lambda name:Bad())
    with pytest.raises(RuntimeError,match='input'):engine.pivot(t)
    assert sha256_file(t.artifact('model.glb'))==digest
    assert not t.artifact('model-pivot.glb').exists()
    assert not t.artifact('model-pivot.pivot-report.json').exists()

def test_pivot_publication_collision_never_quarantines_other_writer(tmp_path,monkeypatch):
    t=task(tmp_path,monkeypatch)
    class Competing(FakePivot):
        def pivot(self,model,output,mode):
            output.write_bytes(b'competitor-owned')
            raise FileExistsError('publication collision')
    monkeypatch.setattr(registry,'get',lambda name:Competing())
    with pytest.raises(FileExistsError):engine.pivot(t)
    assert t.artifact('model-pivot.glb').read_bytes()==b'competitor-owned'

def test_pivot_success_gate_rejects_replacement_and_preserves_competitor(tmp_path,monkeypatch):
    t=task(tmp_path,monkeypatch)
    class Replace(FakePivot):
        def pivot(self,model,output,mode):
            result=super().pivot(model,output,mode)
            replacement=output.with_suffix('.replacement');make_minimal_glb(replacement)
            replacement.replace(output)
            return result
    monkeypatch.setattr(registry,'get',lambda name:Replace())
    with pytest.raises(RuntimeError,match='publication'):engine.pivot(t)
    assert t.artifact('model-pivot.glb').is_file()
    assert not t.artifact('model-pivot.pivot-report.json').exists()

def test_pivot_success_gate_rejects_in_place_content_change(tmp_path,monkeypatch):
    t=task(tmp_path,monkeypatch)
    class Mutate(FakePivot):
        def pivot(self,model,output,mode):
            result=super().pivot(model,output,mode);output.write_bytes(b'corrupt');return result
    monkeypatch.setattr(registry,'get',lambda name:Mutate())
    with pytest.raises(RuntimeError,match='publication'):engine.pivot(t)
    assert not t.artifact('model-pivot.glb').exists()

def test_pivot_invalid_mode_rejected_before_backend(tmp_path,monkeypatch):
    t=task(tmp_path,monkeypatch)
    with pytest.raises(ValueError):engine.pivot(t,mode='guess')

def test_relative_task_failure_owned_outputs_quarantined(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    t=Task.create(__import__('pathlib').Path('tasks'));make_minimal_glb(t.artifact('model.glb'))
    class Bad(FakePivot):
        def pivot(self,model,output,mode):
            result=super().pivot(model,output,mode);model.write_bytes(b'changed');return result
    monkeypatch.setattr(registry,'get',lambda name:Bad())
    with pytest.raises(RuntimeError):engine.pivot(t)
    assert not t.artifact('model-pivot.glb').exists()
    assert not t.artifact('model-pivot.pivot-report.json').exists()

def test_cli_pivot_uses_core(tmp_path,monkeypatch,capsys):
    from openfigura.cli import main
    t=task(tmp_path,monkeypatch)
    assert main(['pivot',str(t.root),'--mode','center'])==0
    data=json.loads(capsys.readouterr().out)
    assert data['mode']=='center' and data['status']=='pass'

def test_mcp_pivot_uses_core(tmp_path,monkeypatch):
    pytest.importorskip('mcp')
    import asyncio
    from openfigura.mcp_server import build
    t=task(tmp_path,monkeypatch)
    result=asyncio.run(build().call_tool('figura_pivot',{'task_root':str(t.root),'mode':'ground'}))
    assert not result.is_error
    assert json.loads(result.content[0].text)['status']=='pass'
