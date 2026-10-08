import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


def backend():
    from openfigura.backends.bake import BakeBackend
    return BakeBackend()


@pytest.mark.parametrize('params', [{'resolution': 63}, {'resolution': 100}, {'resolution': True},
    {'samples': 0}, {'samples': 129}, {'maps': []}, {'maps': ['normal', 'normal']},
    {'maps': ['color']}, {'cage_extrusion': float('nan')}, {'ray_distance': -1}])
def test_invalid_settings_fail_before_process(tmp_path, params):
    high, low = tmp_path/'high.glb', tmp_path/'low.glb'
    high.touch(); low.touch()
    with patch('subprocess.run') as run, pytest.raises(ValueError):
        backend().bake(high, low, tmp_path/'result.glb', params)
    run.assert_not_called()


def test_missing_or_same_inputs_refused(tmp_path):
    high = tmp_path/'high.glb'; high.touch()
    for low in [high, tmp_path/'missing.glb']:
        with pytest.raises(ValueError):
            backend().bake(high, low, tmp_path/'out.glb', {})


@pytest.mark.parametrize('missing', ['output', 'report', 'texture', 'blend'])
def test_success_exit_requires_all_artifacts(tmp_path, missing):
    high, low, out = tmp_path/'high.glb', tmp_path/'low.glb', tmp_path/'out.glb'
    high.touch(); low.touch()
    def run(argv, **kwargs):
        cfg = json.loads(Path(argv[-1]).read_text())
        if missing != 'output': out.write_bytes(b'glb')
        if missing != 'blend': Path(cfg['blend']).touch()
        textures = cfg['textures']
        for path in textures.values():
            if missing != 'texture': Path(path).touch()
        if missing != 'report':
            Path(cfg['report']).write_text(json.dumps({'visual_approval': 'pending'}))
        return SimpleNamespace(returncode=0, stdout='', stderr='')
    with patch.object(type(backend()), 'binary', return_value='blender'), patch('subprocess.run', side_effect=run):
        result = backend().bake(high, low, out, {})
    assert result['exit_code'] != 0
    assert not result['produced']


def test_config_and_valid_success(tmp_path):
    high, low, out = tmp_path/'high.glb', tmp_path/'low.glb', tmp_path/'out.glb'
    high.touch(); low.touch()
    def run(argv, **kwargs):
        assert '--' in argv
        cfg = json.loads(Path(argv[-1]).read_text())
        assert cfg['params']['resolution'] == 512
        assert cfg['params']['maps'] == ['normal', 'ao']
        for path in [cfg['output'], cfg['blend'], *cfg['textures'].values()]: Path(path).touch()
        Path(cfg['report']).write_text(json.dumps({'visual_approval': 'pending'}))
        return SimpleNamespace(returncode=0, stdout='ok', stderr='')
    with patch.object(type(backend()), 'binary', return_value='blender'), patch('subprocess.run', side_effect=run):
        result = backend().bake(high, low, out, {})
    assert result['exit_code'] == 0
    assert result['produced']
    assert result['report']['visual_approval'] == 'pending'


@pytest.mark.parametrize('suffix', ['.glb', '.blend', '.bake-report.json', '-normal.png', '-ao.png'])
def test_existing_artifacts_are_never_overwritten(tmp_path, suffix):
    high, low = tmp_path/'high.glb', tmp_path/'low.glb'
    high.touch(); low.touch()
    artifact = tmp_path/('result'+suffix); artifact.write_bytes(b'keep')
    with patch('subprocess.run') as run, pytest.raises(ValueError):
        backend().bake(high, low, tmp_path/'result.glb', {})
    run.assert_not_called()
    assert artifact.read_bytes() == b'keep'


def test_unavailable_binary_reports_reason(tmp_path):
    high, low = tmp_path/'high.glb', tmp_path/'low.glb'
    high.touch(); low.touch()
    with patch.object(type(backend()), 'binary', return_value=None):
        assert not backend().capabilities().available
        with pytest.raises(RuntimeError, match='unavailable'):
            backend().bake(high, low, tmp_path/'out.glb', {})


def test_optional_albedo_map_is_accepted(tmp_path):
    high, low = tmp_path/'high.glb', tmp_path/'low.glb'
    high.touch(); low.touch()
    def run(argv, **kwargs):
        cfg = json.loads(Path(argv[-1]).read_text())
        assert cfg['params']['maps'] == ['albedo']
        assert set(cfg['textures']) == {'albedo'}
        for path in [cfg['output'], cfg['blend'], *cfg['textures'].values()]: Path(path).touch()
        Path(cfg['report']).write_text(json.dumps({'visual_approval': 'pending'}))
        return SimpleNamespace(returncode=0, stdout='', stderr='')
    with patch.object(type(backend()), 'binary', return_value='blender'), patch('subprocess.run', side_effect=run):
        result = backend().bake(high, low, tmp_path/'out.glb', {'maps': ['albedo']})
    assert result['produced']
