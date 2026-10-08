from pathlib import Path
from openfigura.backends import mia

def test_missing_runtime_is_reported_without_importing_torch(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENFIGURA_MIA_HOME',str(tmp_path/'absent'))
    caps=mia.MiaBackend().capabilities()
    assert not caps.available and 'runtime' in caps.reason

def test_missing_checkpoints_are_not_treated_as_installed(tmp_path,monkeypatch):
    repo=tmp_path/'source';(repo/'.venv-mac/bin').mkdir(parents=True)
    (repo/'model.py').write_text('')
    (repo/'.venv-mac/bin/python').write_text('')
    monkeypatch.setenv('OPENFIGURA_MIA_HOME',str(repo))
    caps=mia.MiaBackend().capabilities()
    assert not caps.available and 'checkpoint' in caps.reason
