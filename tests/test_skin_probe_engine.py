import json
from pathlib import Path
import pytest
from openfigura.core import engine,registry
from openfigura.core.task import Task,sha256_file
from openfigura.core.contracts import AssetRef
from test_engine import make_minimal_glb

CONFIG={'probes':[{'bone':'hand','axis':'X','degrees':30,'track_groups':['leg']}],'resolution':256,'samples':1}

class FakeProbe:
    id='blender-skin-probe'
    def capabilities(self):return registry.Capabilities(True,hardware='cpu')
    def probe(self,model,output,config):
        output.mkdir(parents=True)
        names=['skin-probe-report.json','skin-probe.blend','rest-full.png','probe-001-full.png','probe-001-closeup.png']
        report={'status':'complete','probes':[{'bone':'hand'}],'skin_quality_accepted':False,'collision_checked':False,'collision_accepted':False,'visual_approval':'pending'}
        for name in names:
            p=output/name
            p.write_text(json.dumps(report)) if name.endswith('.json') else p.write_bytes(b'BLENDER-v500' if name.endswith('.blend') else b'\x89PNG\r\n\x1a\n')
        return {'status':'pass','exit_code':0,'produced':True,'report':report,'report_path':str(output/names[0]),'files':names,'wall_seconds':.1,'command':['fake']}

def setup(tmp_path,monkeypatch,backend=None):
    t=Task.create(tmp_path/'tasks');make_minimal_glb(t.artifact('model.glb'))
    monkeypatch.setattr(registry,'get',lambda n:backend or FakeProbe())
    return t

def test_engine_publishes_only_diagnostic_artifacts(tmp_path,monkeypatch):
    t=setup(tmp_path,monkeypatch);before=sha256_file(t.artifact('model.glb'))
    r=engine.skin_probe(t,CONFIG)
    assert r['status']=='pass' and not r['accepted_for_delivery'] and not r['report']['collision_checked']
    assert len(r['output_hashes'])==5 and sha256_file(t.artifact('model.glb'))==before

def test_probe_failure_never_deletes_or_delivers_partial_diagnostics(tmp_path,monkeypatch):
    class Bad(FakeProbe):
        def probe(self,*a):
            r=super().probe(*a);r['report']['status']='fail';return r
    t=setup(tmp_path,monkeypatch,Bad())
    with pytest.raises(RuntimeError):engine.skin_probe(t,CONFIG)
    assert t.entries[-1]['status']=='fail' and list((t.root/'diagnostics').rglob('skin-probe.blend'))

def test_mutated_snapshot_detected_without_changing_source(tmp_path,monkeypatch):
    class Bad(FakeProbe):
        def probe(self,model,*a):
            r=super().probe(model,*a);model.write_bytes(b'changed');return r
    t=setup(tmp_path,monkeypatch,Bad());before=sha256_file(t.artifact('model.glb'))
    with pytest.raises(RuntimeError,match='snapshot'):engine.skin_probe(t,CONFIG)
    assert sha256_file(t.artifact('model.glb'))==before

def test_executor_declares_frames_blend_and_report(tmp_path,monkeypatch):
    t=setup(tmp_path,monkeypatch);ref=AssetRef('artifacts/model.glb',sha256_file(t.artifact('model.glb')),'model','import').to_dict()
    r=engine.execute(t,'skin-probe',[ref],{'config':CONFIG})
    assert {a['kind'] for a in r['outputs']}=={'frame','blend','report'}

def test_backend_cannot_claim_collision_acceptance(tmp_path,monkeypatch):
    class Bad(FakeProbe):
        def probe(self,*a):
            r=super().probe(*a);r['report']['collision_accepted']=True;return r
    t=setup(tmp_path,monkeypatch,Bad())
    with pytest.raises(RuntimeError):engine.skin_probe(t,CONFIG)

def test_cli_probe_calls_engine(tmp_path,monkeypatch,capsys):
    t=setup(tmp_path,monkeypatch);cfg=tmp_path/'config.json';cfg.write_text(json.dumps(CONFIG))
    from openfigura.cli import main
    assert main(['skin-probe',str(t.root),'--config',str(cfg)])==0
    assert not json.loads(capsys.readouterr().out)['accepted_for_delivery']

def test_symlink_diagnostic_parent_refused_before_backend(tmp_path,monkeypatch):
    t=setup(tmp_path,monkeypatch);outside=tmp_path/'outside';outside.mkdir()
    (t.root/'diagnostics').symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError,match='diagnostic'):engine.skin_probe(t,CONFIG)
    assert not list(outside.iterdir())

def test_mcp_probe_uses_engine(tmp_path,monkeypatch):
    import asyncio
    t=setup(tmp_path,monkeypatch)
    from openfigura.mcp_server import build
    r=asyncio.run(build().call_tool('figura_skin_probe',{'task_root':str(t.root),'config':CONFIG}))
    assert not r.is_error and not json.loads(r.content[0].text)['accepted_for_delivery']
