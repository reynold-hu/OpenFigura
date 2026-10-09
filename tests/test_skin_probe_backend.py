import copy
import json
from pathlib import Path
import struct
import subprocess

import pytest

from openfigura.backends.skin_probe import SkinProbeBackend, validate_config


def config():
    return {'probes': [{'bone': 'arm', 'axis': 'X', 'degrees': 30, 'track_groups': ['hand']}]}


def glb(path, **extra):
    doc = {'asset': {'version': '2.0'}, 'buffers': [{'byteLength': 4}], **extra}
    data = json.dumps(doc).encode(); data += b' ' * (-len(data) % 4)
    path.write_bytes(struct.pack('<III', 0x46546c67, 2, 28+len(data)+4) + struct.pack('<II', len(data), 0x4e4f534a) + data + struct.pack('<II', 4, 0x004e4942) + b'\0'*4)
    return path


def test_config_is_copied_and_defaults_explicit():
    value = config(); original = copy.deepcopy(value)
    result = validate_config(value)
    assert result['resolution'] == 512 and result['samples'] == 8
    assert result['crop_extent_ratio'] == .2
    result['probes'][0]['track_groups'].append('other')
    assert value == original


@pytest.mark.parametrize('patch', [
    {'probes': []}, {'probes': config()['probes']*9}, {'resolution': True},
    {'resolution': 255}, {'samples': 129}, {'crop_extent_ratio': float('nan')},
    {'position': [0, 0, 0]}, {'probes': [{'bone': 'a', 'axis': 'x', 'degrees': 2, 'track_groups': ['a']}]},
    {'probes': [{'bone': '', 'axis': 'X', 'degrees': 2, 'track_groups': ['a']}]},
    {'probes': [{'bone': 'a', 'axis': 'X', 'degrees': 0, 'track_groups': ['a']}]},
    {'probes': [{'bone': 'a', 'axis': 'X', 'degrees': float('inf'), 'track_groups': ['a']}]},
    {'probes': [{'bone': 'a', 'axis': 'X', 'degrees': 181, 'track_groups': ['a']}]},
    {'probes': [{'bone': 'a', 'axis': 'X', 'degrees': 2, 'track_groups': ['a', 'a']}]},
    {'probes': [{'bone': 'a', 'axis': 'X', 'degrees': 2, 'track_groups': [], 'extra': 2}]},
])
def test_invalid_config_rejected(patch):
    with pytest.raises(ValueError): validate_config({**config(), **patch})


@pytest.mark.parametrize('extra', [{'animations': [{}]}, {'images': [{'uri': 'secret.png'}]}, {'buffers': [{'uri': 'x.bin', 'byteLength': 4}]}])
def test_unsafe_glb_rejected_before_blender(tmp_path, extra):
    source = glb(tmp_path/'model.glb', **extra)
    with pytest.raises(ValueError): SkinProbeBackend().probe(source, tmp_path/'out', config())
    assert not (tmp_path/'out').exists()


def test_existing_output_refused(tmp_path):
    source = glb(tmp_path/'model.glb'); out = tmp_path/'out'; out.mkdir()
    with pytest.raises(ValueError): SkinProbeBackend().probe(source, out, config())


@pytest.mark.parametrize('report', [None, {'status': 'failed'}, {'status': 'complete'}, {'status': 'complete', 'probes': []}])
def test_exit_zero_does_not_replace_completion_report(tmp_path, monkeypatch, report):
    backend = SkinProbeBackend(); monkeypatch.setattr(backend, 'binary', lambda: '/blender')
    def run(argv, **kwargs):
        cfg = json.loads(Path(argv[-1]).read_text()); out = Path(cfg['output_dir'])
        if report is not None: (out/'skin-probe-report.json').write_text(json.dumps(report))
        return subprocess.CompletedProcess(argv, 0, '', 'Python failed')
    monkeypatch.setattr(subprocess, 'run', run)
    result = backend.probe(glb(tmp_path/'model.glb'), tmp_path/'out', config())
    assert result['status'] == 'fail' and result['exit_code'] != 0


def test_complete_requires_expected_artifacts_and_flags(tmp_path, monkeypatch):
    backend = SkinProbeBackend(); monkeypatch.setattr(backend, 'binary', lambda: '/blender')
    def run(argv, **kwargs):
        cfg = json.loads(Path(argv[-1]).read_text()); out = Path(cfg['output_dir'])
        report = valid_report()
        import hashlib
        report['source_sha256'] = hashlib.sha256(Path(cfg['model']).read_bytes()).hexdigest()
        (out/'skin-probe-report.json').write_text(json.dumps(report))
        for name in ['skin-probe.blend', 'rest-full.png', 'probe-001-full.png', 'probe-001-closeup.png']: (out/name).write_bytes(b'artifact')
        return subprocess.CompletedProcess(argv, 0, '', '')
    monkeypatch.setattr(subprocess, 'run', run)
    result = backend.probe(glb(tmp_path/'model.glb'), tmp_path/'out', config())
    assert result['status'] == 'pass' and result['exit_code'] == 0
    assert len(result['files']) == 5


def test_displacement_statistics_preserve_labels_and_strict_threshold():
    from openfigura.backends.skin_probe_worker import displacement_report
    result = displacement_report([(0,0,0)]*3, [(0,0,0), (.002,0,0), (.003,0,0)], [0,1,2], ['root','hand','finger'])
    assert result['tracked_vertices'] == 3
    assert result['over_002_world_units'] == 1
    assert result['peak_world_units'] == .003
    assert result['worst_samples'][0]['vertex_index'] == 2
    assert result['worst_samples'][0]['original_dominant_group'] == 'finger'
    assert result['worst_samples'][0]['rest_world'] == [0,0,0]


def test_displacement_rejects_changed_topology():
    from openfigura.backends.skin_probe_worker import displacement_report
    with pytest.raises(ValueError): displacement_report([(0,0,0)], [], [0], ['hand'])


def test_report_complete_rejects_malformed_mesh_statistics():
    from openfigura.backends.skin_probe import report_complete
    value = {'schema_version': 1, 'status': 'complete', 'probes': [{**config()['probes'][0], 'meshes': [None]}], 'skin_quality_accepted': False, 'collision_checked': False, 'collision_accepted': False, 'visual_approval': 'pending'}
    assert report_complete(value, validate_config(config())) is False


def test_displacement_rejects_nonfinite_coordinates():
    from openfigura.backends.skin_probe_worker import displacement_report
    with pytest.raises(ValueError): displacement_report([(0,0,0)], [(float('nan'),0,0)], [0], ['hand'])


@pytest.mark.parametrize('patch', [{'crop_extent_ratio': 10**1000}, {'probes': [{'bone': 'a', 'axis': 'X', 'degrees': 10**1000, 'track_groups': ['a']}]}])
def test_unrepresentable_config_numeric_rejected(patch):
    with pytest.raises(ValueError): validate_config({**config(), **patch})


def test_full_frame_covers_deformed_bounds():
    from openfigura.backends.skin_probe_worker import frame_bounds
    center, scale = frame_bounds([(-.5,-.5,0), (.5,.5,1.116)])
    assert center == [0,0,.558]
    assert scale > 1.116



def valid_report():
    return {'schema_version': 1, 'status': 'complete', 'settings': validate_config(config()),
            'source_sha256': 'a'*64, 'source_unchanged': True,
            'baseline': [{'mesh': 'Mesh', 'vertices': 1, 'world_positions_sha256': 'b'*64, 'original_labels_sha256': 'c'*64}],
            'probes': [{**config()['probes'][0], 'meshes': [{'mesh': 'Mesh', 'tracked_vertices': 1, 'peak_world_units': .1,
            'quantiles_world_units': {'0.5': .1, '0.9': .1, '0.95': .1, '0.99': .1}, 'over_002_world_units': 1,
            'worst_samples': [{'vertex_index': 0, 'original_dominant_group': 'hand', 'rest_world': [0,0,0], 'posed_world': [.1,0,0], 'displacement_world_units': .1}],
            'frozen_track_mask_sha256': 'd'*64}]}], 'skin_quality_accepted': False, 'collision_checked': False,
            'collision_accepted': False, 'visual_approval': 'pending'}


def test_direct_backend_refuses_immediate_symlink_parent(tmp_path, monkeypatch):
    backend = SkinProbeBackend(); monkeypatch.setattr(backend, 'binary', lambda: '/blender')
    dest = tmp_path/'outside'; dest.mkdir(); alias = tmp_path/'alias'; alias.symlink_to(dest, target_is_directory=True)
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: pytest.fail('Blender must not start'))
    with pytest.raises(ValueError, match='symlink'):
        backend.probe(glb(tmp_path/'model.glb'), alias/'probe', config())
    assert not (dest/'probe').exists()


@pytest.mark.parametrize('mutation', ['source', 'settings', 'baseline', 'sample', 'coordinates', 'quantiles', 'peak', 'sample_label', 'sample_count', 'sample_id'])
def test_completion_rejects_malformed_semantic_fields(mutation):
    from openfigura.backends.skin_probe import report_complete
    report = valid_report(); mesh = report['probes'][0]['meshes'][0]
    if mutation == 'source': report['source_sha256'] = 'wrong'
    elif mutation == 'settings': report['settings']['samples'] = 2
    elif mutation == 'baseline': report['baseline'] = [{'mesh': 'Mesh', 'vertices': 0}]
    elif mutation == 'sample': mesh['worst_samples'] = [None]
    elif mutation == 'coordinates': mesh['worst_samples'][0]['posed_world'] = [float('nan'),0,0]
    elif mutation == 'quantiles': mesh['quantiles_world_units']['0.5'] = .2
    elif mutation == 'peak': mesh['peak_world_units'] = 10**1000
    elif mutation == 'sample_label': mesh['worst_samples'][0]['original_dominant_group'] = []
    elif mutation == 'sample_count': mesh['worst_samples'] = []
    elif mutation == 'sample_id': mesh['worst_samples'][0]['vertex_index'] = 1
    assert report_complete(report, validate_config(config())) is False
