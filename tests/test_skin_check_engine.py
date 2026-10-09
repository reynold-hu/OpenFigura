import asyncio,json,sys,types
import pytest
from openfigura.core import engine
from openfigura.core.task import Task,sha256_file
from openfigura.core.contracts import AssetRef
from test_engine import make_minimal_glb

CONFIG={'families':{'hand':['hand'],'leg':['leg']},'pairs':[['hand','leg']]}

def setup(tmp_path,monkeypatch,parser=None):
    t=Task.create(tmp_path/'tasks');make_minimal_glb(t.artifact('model.glb'))
    def fake(path,families,pairs,**options):
        return {'assessment':'suspicious','vertices':1,'source_sha256':sha256_file(path),'reports':[],
                'skin_quality_accepted':False,'collision_checked':False,'visual_approval':'pending'}
    monkeypatch.setitem(sys.modules,'openfigura.core.glb_skin',types.SimpleNamespace(analyze_glb_weights=parser or fake))
    return t

def test_engine_publishes_readonly_diagnostic_report(tmp_path,monkeypatch):
    t=setup(tmp_path,monkeypatch);before=sha256_file(t.artifact('model.glb'))
    r=engine.skin_check(t,CONFIG)
    assert r['status']=='pass' and r['assessment']=='suspicious' and not r['skin_quality_accepted']
    assert json.loads((t.root/r['report_path']).read_text())['assessment']=='suspicious'
    assert sha256_file(t.artifact('model.glb'))==before
    with pytest.raises(FileExistsError):engine.skin_check(t,CONFIG)

def test_input_mutation_isolated_and_report_not_published(tmp_path,monkeypatch):
    def bad(path,*a,**kw):path.write_bytes(b'mutated');return {'source_sha256':'wrong','assessment':'suspicious'}
    t=setup(tmp_path,monkeypatch,bad);before=sha256_file(t.artifact('model.glb'))
    with pytest.raises(RuntimeError,match='snapshot'):engine.skin_check(t,CONFIG)
    assert sha256_file(t.artifact('model.glb'))==before and not t.artifact('model-skin-check.json').exists()

@pytest.mark.parametrize('config',[{}, {'families':{},'pairs':[]}, {**CONFIG,'unknown':True}])
def test_bad_config_rejected(tmp_path,monkeypatch,config):
    t=setup(tmp_path,monkeypatch)
    with pytest.raises(ValueError):engine.skin_check(t,config)

def test_execute_declares_only_report_and_keeps_assessment(tmp_path,monkeypatch):
    t=setup(tmp_path,monkeypatch)
    ref=AssetRef('artifacts/model.glb',sha256_file(t.artifact('model.glb')),'model','import').to_dict()
    r=engine.execute(t,'skin-check',[ref],{'config':CONFIG})
    assert r['status']=='pass' and {a['kind'] for a in r['outputs']}=={'report'}
    report=json.loads((t.root/r['outputs'][0]['task_relative_path']).read_text())
    assert report['assessment']=='suspicious' and not report['skin_quality_accepted']

def test_cli_and_mcp_are_engine_mirrors(tmp_path,monkeypatch,capsys):
    t=setup(tmp_path,monkeypatch);cfg=tmp_path/'config.json';cfg.write_text(json.dumps(CONFIG))
    from openfigura.cli import main
    assert main(['skin-check',str(t.root),'--config',str(cfg)])==0
    assert json.loads(capsys.readouterr().out)['assessment']=='suspicious'
    other=setup(tmp_path/'other',monkeypatch)
    from openfigura.mcp_server import build
    result=asyncio.run(build().call_tool('figura_skin_check',{'task_root':str(other.root),'config':CONFIG}))
    assert not result.is_error and json.loads(result.content[0].text)['assessment']=='suspicious'

def test_publication_competitor_is_preserved(tmp_path,monkeypatch):
    t=setup(tmp_path,monkeypatch)
    def compete(source,dest):
        from pathlib import Path
        Path(dest).write_text('competitor')
        raise FileExistsError('other writer won')
    monkeypatch.setattr(engine.os,'link',compete)
    with pytest.raises(FileExistsError):engine.skin_check(t,CONFIG)
    assert t.artifact('model-skin-check.json').read_text()=='competitor'

def test_replaced_report_is_rejected_without_deleting_other_writer(tmp_path,monkeypatch):
    t=setup(tmp_path,monkeypatch);link=engine.os.link
    def replace(source,dest):
        from pathlib import Path
        link(source,dest);replacement=Path(dest).with_suffix('.replacement');replacement.write_text('competitor');replacement.replace(dest)
    monkeypatch.setattr(engine.os,'link',replace)
    with pytest.raises(RuntimeError,match='publication'):engine.skin_check(t,CONFIG)
    assert t.artifact('model-skin-check.json').read_text()=='competitor'

def test_diagnostic_cannot_claim_collision_acceptance(tmp_path,monkeypatch):
    def bad(path,*a,**kw):return {'source_sha256':sha256_file(path),'assessment':'no_flagged_conflicts','skin_quality_accepted':False,'collision_checked':True}
    t=setup(tmp_path,monkeypatch,bad)
    with pytest.raises(RuntimeError,match='cannot accept'):engine.skin_check(t,CONFIG)
    assert not t.artifact('model-skin-check.json').exists()

def test_undeclared_execute_input_rejected(tmp_path,monkeypatch):
    t=setup(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='declared'):engine.execute(t,'skin-check',[],{'config':CONFIG})

def test_cached_diagnostic_report_reuses_only_verified_output(tmp_path,monkeypatch):
    t=setup(tmp_path,monkeypatch);ref=AssetRef('artifacts/model.glb',sha256_file(t.artifact('model.glb')),'model','import').to_dict()
    first=engine.execute(t,'skin-check',[ref],{'config':CONFIG})
    second=engine.execute(t,'skin-check',[ref],{'config':CONFIG})
    assert second['cached_from']==first['stage_id']
