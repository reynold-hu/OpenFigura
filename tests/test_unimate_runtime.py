from pathlib import Path
from unittest.mock import patch

import pytest

from openfigura.backends import base
from openfigura.core import registry  # bootstrap registered backends before direct import
from openfigura.backends.unimate import UnimateBackend


def result(argv, code=0, stdout='', stderr=''):
    return base.CommandResult(argv, code, .1, stdout, stderr)


def configured(tmp_path):
    backend = UnimateBackend()
    backend.paths = lambda: (tmp_path/'repo', tmp_path/'chosen-python', tmp_path/'ckpt')
    return backend


def test_failed_preprocess_never_samples_even_with_annotation(tmp_path):
    with patch('openfigura.backends.unimate.base.run', side_effect=lambda argv, **kw: result(argv, 7, stderr='preprocess failed')) as run:
        report = configured(tmp_path).generate_motion(tmp_path/'rig.glb', tmp_path/'work', 'walk', 1, 2., 0, 'annotation.json')
    assert run.call_count == 1
    assert report['status'] == 'fail' and not report['produced']
    assert report['steps']['rig_preprocess']['exit_code'] == 7
    assert 'preprocess failed' in report['stderr_tail']


def test_manifest_and_drive_use_selected_python_and_blender(tmp_path):
    backend = configured(tmp_path)
    calls=[]
    anim, char, cond = [tmp_path/name for name in ['motion.npy', 'character.glb', 'cond.npy']]
    for path in [anim, char, cond]: path.touch()
    def run(argv, **kwargs):
        calls.append(argv)
        if 'data_process.mesh_animation.sample_manifest' in ' '.join(argv):
            Path(argv[-1]).write_text('\t'.join(map(str, [anim, char, cond]))+'\tgeneral\n')
        if argv[0] == '/selected/blender':
            output = Path(argv[argv.index('--output_dir')+1]);output.mkdir(parents=True, exist_ok=True)
            (output/'motion.glb').touch();(output/'motion.fbx').touch()
        return result(argv)
    with patch.object(backend, 'blender_binary', return_value='/selected/blender'), patch('openfigura.backends.unimate.base.run', side_effect=run):
        report = backend.generate_motion(tmp_path/'rig.glb', tmp_path/'work', 'walk', 1, 2., 0, 'annotation.json')
    assert report['produced'] and report['status'] == 'pass'
    assert all(argv[0] == str(tmp_path/'chosen-python') for argv in calls[:-1])
    assert calls[-1][0] == '/selected/blender'
    assert '--python-exit-code' in calls[-1]
    assert '--char_path' in calls[-1] and '--cond_path' in calls[-1]
    assert not any('bash' in argv or 'conda' in argv for argv in calls)


def test_failed_manifest_never_drives(tmp_path):
    backend = configured(tmp_path)
    def run(argv, **kwargs):
        return result(argv, 4 if 'data_process.mesh_animation.sample_manifest' in ' '.join(argv) else 0)
    with patch.object(backend, 'blender_binary', return_value='/selected/blender'), patch('openfigura.backends.unimate.base.run', side_effect=run) as process:
        report = backend.generate_motion(tmp_path/'rig.glb', tmp_path/'work', 'walk', 1, 2., 0, 'annotation.json')
    assert not report['produced']
    assert all(call.args[0][0] != '/selected/blender' for call in process.call_args_list)


@pytest.mark.parametrize('job_text', ['', 'invalid\trow', 'missing.npy\tmissing.glb\tmissing-cond.npy\tgeneral'])
def test_invalid_manifest_jobs_fail_before_blender(tmp_path, job_text):
    backend = configured(tmp_path)
    def run(argv, **kwargs):
        if 'data_process.mesh_animation.sample_manifest' in ' '.join(argv): Path(argv[-1]).write_text(job_text)
        return result(argv)
    with patch.object(backend, 'blender_binary', return_value='/selected/blender'), patch('openfigura.backends.unimate.base.run', side_effect=run) as process:
        report = backend.generate_motion(tmp_path/'rig.glb', tmp_path/'work', 'walk', 1, 2., 0, 'annotation.json')
    assert report['status'] == 'fail' and not report['produced']
    assert all(call.args[0][0] != '/selected/blender' for call in process.call_args_list)


@pytest.mark.parametrize('failure', ['nonzero', 'missing-glb', 'missing-fbx'])
def test_blender_failure_or_missing_expected_artifacts_is_failure(tmp_path, failure):
    backend = configured(tmp_path)
    anim, char, cond = [tmp_path/name for name in ['motion.npy', 'character.glb', 'cond.npy']]
    for path in [anim, char, cond]: path.touch()
    def run(argv, **kwargs):
        if 'data_process.mesh_animation.sample_manifest' in ' '.join(argv):
            Path(argv[-1]).write_text('\t'.join(map(str, [anim, char, cond]))+'\tgeneral\n')
        if argv[0] == '/selected/blender':
            output = Path(argv[argv.index('--output_dir')+1])
            if failure != 'missing-glb': (output/'motion.glb').touch()
            if failure != 'missing-fbx': (output/'motion.fbx').touch()
            return result(argv, 9 if failure == 'nonzero' else 0)
        return result(argv)
    with patch.object(backend, 'blender_binary', return_value='/selected/blender'), patch('openfigura.backends.unimate.base.run', side_effect=run):
        report = backend.generate_motion(tmp_path/'rig.glb', tmp_path/'work', 'walk', 1, 2., 0, 'annotation.json')
    assert report['status'] == 'fail' and not report['produced']
    assert report['steps']['drive']['exit_code'] != 0


def test_missing_blender_returns_unavailable_without_shell_fallback(tmp_path):
    backend = configured(tmp_path)
    with patch.object(backend, 'blender_binary', return_value=None), patch('openfigura.backends.unimate.base.run', side_effect=lambda argv, **kw: result(argv)) as process:
        report = backend.generate_motion(tmp_path/'rig.glb', tmp_path/'work', 'walk', 1, 2., 0, 'annotation.json')
    assert report['status'] == 'unavailable' and not report['produced']
    assert process.call_count == 2


def test_manifest_paths_resolve_from_upstream_repo_not_agent_cwd(tmp_path):
    backend = configured(tmp_path)
    repo = tmp_path/'repo';repo.mkdir()
    for name in ['motion.npy', 'character.glb', 'cond.npy']: (repo/name).touch()
    def run(argv, **kwargs):
        if 'data_process.mesh_animation.sample_manifest' in ' '.join(argv):
            Path(argv[-1]).write_text('motion.npy\tcharacter.glb\tcond.npy\tgeneral\n')
        if argv[0] == '/selected/blender':
            assert argv[argv.index('--char_path')+1] == str(repo/'character.glb')
            output = Path(argv[argv.index('--output_dir')+1])
            (output/'motion.glb').touch();(output/'motion.fbx').touch()
        return result(argv)
    with patch.object(backend, 'blender_binary', return_value='/selected/blender'), patch('openfigura.backends.unimate.base.run', side_effect=run):
        report = backend.generate_motion(tmp_path/'rig.glb', tmp_path/'work', 'walk', 1, 2., 0, 'annotation.json')
    assert report['produced']
