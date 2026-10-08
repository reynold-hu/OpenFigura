import json

from openfigura.backends.pixal3d import Pixal3DBackend


def profile(tmp_path, monkeypatch):
    runtime = tmp_path / 'trellis-cli'
    runtime.write_text('#!/bin/sh\nexit 0\n')
    runtime.chmod(0o755)
    models = tmp_path / 'models'; models.mkdir()
    path = tmp_path / 'pixal.json'
    path.write_text(json.dumps({'schema_version': 1, 'runtime': str(runtime), 'models': str(models)}))
    monkeypatch.setenv('OPENFIGURA_PIXAL_PROFILE', str(path))
    monkeypatch.delenv('OPENFIGURA_PIXAL_RUNTIME', raising=False)
    monkeypatch.delenv('OPENFIGURA_PIXAL_MODELS', raising=False)
    monkeypatch.setattr('openfigura.backends.pixal3d.base.which', lambda name: None)
    return runtime, models, path


def test_profile_discovers_existing_install(tmp_path, monkeypatch):
    runtime, models, path = profile(tmp_path, monkeypatch)
    backend = Pixal3DBackend()
    assert backend.capabilities().available
    assert backend.runtime_path() == runtime and backend.models_dir() == models


def test_explicit_env_overrides_profile_even_when_invalid(tmp_path, monkeypatch):
    profile(tmp_path, monkeypatch)
    monkeypatch.setenv('OPENFIGURA_PIXAL_RUNTIME', '/missing/explicit/runtime')
    assert not Pixal3DBackend().capabilities().available


def test_bad_profile_is_unavailable_not_crash(tmp_path, monkeypatch):
    _, _, path = profile(tmp_path, monkeypatch)
    path.write_text('{invalid')
    caps = Pixal3DBackend().capabilities()
    assert not caps.available and 'profile' in caps.reason
