"""CPU pivot contract: real GLB geometry, attribute preservation and refusal."""
import hashlib
import importlib
import json
import math
import os
import struct

import pytest

from openfigura.core.glb_faces import _read


def fixture(path, mutate=None, positions=None):
    positions = positions or [(1., 2., 3.), (5., 2., 3.), (1., 6., 7.)]
    blob = b''.join(struct.pack('<fffI', *p, 0x12345678) for p in positions)
    blob += struct.pack('<HHH', 0, 1, 2) + b'\0\0'
    doc = {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': [0]}],
           'nodes': [{'mesh': 0, 'name': 'original'}],
           'meshes': [{'primitives': [{'attributes': {'POSITION': 0}, 'indices': 1}]}],
           'materials': [{'name': 'preserved'}],
           'buffers': [{'byteLength': len(blob)}],
           'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': 48, 'byteStride': 16},
                           {'buffer': 0, 'byteOffset': 48, 'byteLength': 6}],
           'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': 3, 'type': 'VEC3',
                          'min': [-999]*3, 'max': [999]*3},
                         {'bufferView': 1, 'componentType': 5123, 'count': 3, 'type': 'SCALAR'}]}
    if mutate:
        mutate(doc)
    encoded = json.dumps(doc, allow_nan=True).encode()
    encoded += b' ' * (-len(encoded) % 4)
    raw = (struct.pack('<III', 0x46546C67, 2, 28 + len(encoded) + len(blob)) +
           struct.pack('<II', len(encoded), 0x4E4F534A) + encoded +
           struct.pack('<II', len(blob), 0x004E4942) + blob)
    path.write_bytes(raw)
    return raw, doc, blob


def backend():
    return importlib.import_module('openfigura.backends.glb_pivot').PivotBackend()


def test_backend_exists_and_cpu_available():
    assert importlib.util.find_spec('openfigura.backends.glb_pivot') is not None
    caps = backend().capabilities()
    assert backend().id == 'gltf-pivot'
    assert backend().kind == 'postprocess'
    assert caps.available and caps.hardware == 'cpu'


@pytest.mark.parametrize('mode,translation,after_min,after_max', [
    ('ground', [-3., -2., -5.], [-2., 0., -2.], [2., 4., 2.]),
    ('center', [-3., -4., -5.], [-2., -2., -2.], [2., 2., 2.]),
])
def test_bounds_decode_stride_and_preserve_every_attribute(tmp_path, mode, translation, after_min, after_max):
    source, out = tmp_path/'source.glb', tmp_path/'pivot.glb'
    raw, original, blob = fixture(source)
    result = backend().pivot(source, out, mode)
    _, changed, changed_blob = _read(out)
    assert source.read_bytes() == raw
    assert changed_blob == blob
    assert changed['nodes'][:-2] == original['nodes']
    assert changed['nodes'][-2]['translation'] == translation
    assert changed['nodes'][-2]['children'] == [0]
    assert changed['scenes'][0]['nodes'] == [2]
    for key in ('meshes', 'materials', 'accessors', 'bufferViews', 'buffers'):
        assert changed[key] == original[key]
    report = result['report']
    assert report['bounds_before'] == {'min': [1., 2., 3.], 'max': [5., 6., 7.]}
    assert report['bounds_after'] == {'min': after_min, 'max': after_max}
    assert report['world_translation'] == translation
    assert report['attribute_bytes_preserved'] is True
    assert report['visual_approval'] == 'pending'
    assert result['source_sha256'] == hashlib.sha256(raw).hexdigest()
    assert result['output_sha256'] == hashlib.sha256(out.read_bytes()).hexdigest()
    assert result['exit_code'] == 0 and result['produced'] is True
    assert result['wall_seconds'] >= 0
    assert json.loads(out.with_suffix('.pivot-report.json').read_text()) == report


def test_nested_quaternion_negative_scale_and_matrix(tmp_path):
    source, out = tmp_path/'source.glb', tmp_path/'pivot.glb'
    def mutate(doc):
        doc['nodes'] = [
            {'children': [1], 'translation': [10, 20, 30], 'rotation': [0, 0, math.sqrt(.5), math.sqrt(.5)], 'scale': [-2, 3, 1]},
            {'mesh': 0, 'matrix': [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 1, 2, 3, 1]}]
    fixture(source, mutate)
    result = backend().pivot(source, out)
    assert result['report']['bounds_before']['min'] == pytest.approx([-14., 8., 36.])
    assert result['report']['bounds_before']['max'] == pytest.approx([-2., 16., 40.])
    assert result['report']['world_translation'] == pytest.approx([8., -8., -38.])


@pytest.mark.parametrize('mutate', [
    lambda d: d['scenes'].append({'nodes': [0]}),
    lambda d: d.update(animations=[{}]),
    lambda d: d.update(skins=[{}]),
    lambda d: d['nodes'][0].update(skin=0),
    lambda d: d['nodes'][0].update(children=[0]),
    lambda d: d['nodes'].extend([{'children': [0]}, {'children': [0]}]),
    lambda d: d['scenes'][0].update(nodes=[0, 0]),
    lambda d: d['nodes'][0].update(children=[99]),
    lambda d: d['meshes'][0]['primitives'][0].update(targets=[{}]),
    lambda d: d['meshes'][0]['primitives'][0].update(mode=0),
    lambda d: d['meshes'][0]['primitives'][0].update(extensions={'KHR_draco_mesh_compression': {}}),
    lambda d: d['bufferViews'][0].update(extensions={'EXT_meshopt_compression': {}}),
    lambda d: d['accessors'][0].update(byteOffset=44),
    lambda d: d['accessors'][0].update(count=10**30),
    lambda d: d['accessors'][0].update(sparse={}),
    lambda d: d['accessors'][0].update(componentType=5123),
    lambda d: d['nodes'][0].update(translation=[float('nan'), 0, 0]),
    lambda d: d['nodes'][0].update(rotation=[0, 0, 0, 0]),
    lambda d: d['nodes'][0].update(matrix=[1]*16),
    lambda d: d['nodes'][0].update(matrix=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1], translation=[0,0,0]),
])
def test_invalid_or_unsupported_refused_without_output(tmp_path, mutate):
    source, out = tmp_path/'source.glb', tmp_path/'pivot.glb'
    fixture(source, mutate)
    with pytest.raises(ValueError):
        backend().pivot(source, out)
    assert not out.exists()
    assert not out.with_suffix('.pivot-report.json').exists()


def test_nonfinite_position_refused(tmp_path):
    source, out = tmp_path/'source.glb', tmp_path/'pivot.glb'
    fixture(source, positions=[(float('nan'), 2, 3), (5,2,3), (1,6,7)])
    with pytest.raises(ValueError):
        backend().pivot(source, out)
    assert not out.exists()


@pytest.mark.parametrize('collision', ['output', 'dangling', 'source_alias', 'report', 'report_dangling'])
def test_existing_or_symlink_outputs_refused(tmp_path, collision):
    source, out = tmp_path/'source.glb', tmp_path/'pivot.glb'
    fixture(source)
    report = out.with_suffix('.pivot-report.json')
    if collision == 'output':
        out.write_bytes(b'owner')
    elif collision == 'dangling':
        out.symlink_to(tmp_path/'absent')
    elif collision == 'source_alias':
        out.symlink_to(source)
    elif collision == 'report':
        report.write_bytes(b'owner')
    else:
        report.symlink_to(tmp_path/'absent')
    with pytest.raises((ValueError, FileExistsError)):
        backend().pivot(source, out)
    assert source.exists()


def test_concurrent_report_publication_rolls_back_only_own_output(tmp_path, monkeypatch):
    source, out = tmp_path/'source.glb', tmp_path/'pivot.glb'
    fixture(source)
    original_link = os.link
    report = out.with_suffix('.pivot-report.json')
    def racing_link(src, dst, *args, **kwargs):
        if str(dst) == str(report):
            report.symlink_to(tmp_path/'absent')
        return original_link(src, dst, *args, **kwargs)
    monkeypatch.setattr(os, 'link', racing_link)
    with pytest.raises(FileExistsError):
        backend().pivot(source, out)
    assert not out.exists()
    assert report.is_symlink()


@pytest.mark.parametrize('mutate', [
    lambda d: d['nodes'].__setitem__(0, None),
    lambda d: d['accessors'].__setitem__(0, None),
    lambda d: d['nodes'][0].update(children=[True]),
    lambda d: d['nodes'][0].update(children=[-1]),
    lambda d: d.update(extensionsRequired=['UNKNOWN_geometry']),
    lambda d: d['nodes'][0].update(extensions={'EXT_mesh_gpu_instancing': {}}),
    lambda d: d['meshes'][0]['primitives'][0].pop('indices'),
    lambda d: d['meshes'][0]['primitives'][0].update(indices=99),
])
def test_malformed_structures_or_extension_semantics_refused(tmp_path, mutate):
    source, out = tmp_path/'source.glb', tmp_path/'pivot.glb'
    fixture(source, mutate)
    with pytest.raises(ValueError):
        backend().pivot(source, out)
    assert not out.exists()


def test_material_extensions_preserved(tmp_path):
    source, out = tmp_path/'source.glb', tmp_path/'pivot.glb'
    def mutate(d):
        d['extensionsRequired'] = ['KHR_materials_unlit', 'KHR_texture_transform']
        d['materials'][0]['extensions'] = {'KHR_materials_unlit': {}}
    _, original, _ = fixture(source, mutate)
    backend().pivot(source, out)
    _, changed, _ = _read(out)
    assert changed['materials'] == original['materials']
    assert changed['extensionsRequired'] == original['extensionsRequired']


def test_two_scene_roots_sharing_mesh_have_combined_actual_bounds(tmp_path):
    source, out = tmp_path/'source.glb', tmp_path/'pivot.glb'
    def mutate(d):
        d['nodes'].append({'mesh': 0, 'translation': [10, -5, 20]})
        d['scenes'][0]['nodes'] = [0, 1]
    fixture(source, mutate)
    result = backend().pivot(source, out)
    assert result['report']['bounds_before'] == {'min': [1., -3., 3.], 'max': [15., 6., 27.]}
    _, changed, _ = _read(out)
    assert changed['nodes'][-2]['children'] == [0, 1]


def test_concurrent_output_publication_preserves_competing_symlink(tmp_path, monkeypatch):
    source, out = tmp_path/'source.glb', tmp_path/'pivot.glb'
    fixture(source)
    original_link = os.link
    def racing_link(src, dst, *args, **kwargs):
        if str(dst) == str(out):
            out.symlink_to(tmp_path/'absent')
        return original_link(src, dst, *args, **kwargs)
    monkeypatch.setattr(os, 'link', racing_link)
    with pytest.raises(FileExistsError):
        backend().pivot(source, out)
    assert out.is_symlink()
    assert not out.with_suffix('.pivot-report.json').exists()
    assert not list(tmp_path.glob('.pivot-*'))


def test_invalid_mode_refused(tmp_path):
    source, out = tmp_path/'source.glb', tmp_path/'pivot.glb'
    fixture(source)
    with pytest.raises(ValueError, match='mode'):
        backend().pivot(source, out, 'unknown')
    assert not out.exists()


def test_external_image_sidecar_refused(tmp_path):
    source, out = tmp_path/'source.glb', tmp_path/'pivot.glb'
    fixture(source, lambda d: d.update(images=[{'uri': 'texture.png'}]))
    with pytest.raises(ValueError, match='external image'):
        backend().pivot(source, out)
    assert not out.exists()


def test_embedded_data_uri_image_preserved(tmp_path):
    source, out = tmp_path/'source.glb', tmp_path/'pivot.glb'
    _, original, _ = fixture(source, lambda d: d.update(images=[{'uri': 'data:image/png;base64,AA=='}]))
    backend().pivot(source, out)
    _, changed, _ = _read(out)
    assert changed['images'] == original['images']


def test_strided_index_view_refused_before_output(tmp_path):
    source, out = tmp_path/'source.glb', tmp_path/'pivot.glb'
    fixture(source, lambda d: d['bufferViews'][1].update(byteStride=2))
    with pytest.raises(ValueError, match='byteStride'):
        backend().pivot(source, out)
    assert not out.exists()
    assert not out.with_suffix('.pivot-report.json').exists()


@pytest.mark.parametrize('mode', ['ground', 'center'])
def test_asset_identity_root_rotates_about_new_origin(tmp_path, mode):
    from openfigura.backends.glb_pivot import _bounds
    source, out = tmp_path/'source.glb', tmp_path/'pivot.glb'
    _, original, _ = fixture(source)
    result = backend().pivot(source, out, mode)
    _, changed, blob = _read(out)
    assert changed['nodes'][:len(original['nodes'])] == original['nodes']
    assert len(changed['nodes']) == len(original['nodes']) + 2
    asset_root = changed['scenes'][0]['nodes'][0]
    assert result['report']['asset_root_node'] == asset_root
    assert result['report']['pivot_world_origin'] == [0., 0., 0.]
    root = changed['nodes'][asset_root]
    assert root['name'] == 'OpenFiguraPivot'
    assert root.get('translation', [0., 0., 0.]) == [0., 0., 0.]
    offset = changed['nodes'][root['children'][0]]
    assert offset['translation'] == result['report']['world_translation']
    assert offset['children'] == [0]
    # A half-turn about world Y keeps the ground anchor at world zero and
    # horizontal mesh bounds centered there. Previous Tdelta*R root did not.
    root['rotation'] = [0., 1., 0., 0.]
    rotated = _bounds(changed, blob)
    assert (rotated['min'][0]+rotated['max'][0])/2 == pytest.approx(0.)
    assert (rotated['min'][2]+rotated['max'][2])/2 == pytest.approx(0.)
    if mode == 'ground':
        assert rotated['min'][1] == pytest.approx(0.)
    else:
        assert (rotated['min'][1]+rotated['max'][1])/2 == pytest.approx(0.)


def test_publication_returns_actual_owned_artifact_identities(tmp_path):
    source, out = tmp_path/'source.glb', tmp_path/'pivot.glb'
    fixture(source)
    result = backend().pivot(source, out)
    for path in (out, out.with_suffix('.pivot-report.json')):
        st = path.lstat()
        assert result['owned_artifacts'][str(path)] == [st.st_dev, st.st_ino]


def test_owned_identity_does_not_adopt_concurrent_replacement(tmp_path, monkeypatch):
    source, out = tmp_path/'source.glb', tmp_path/'pivot.glb'
    fixture(source)
    original_link = os.link
    captured = {}
    def replacing_link(src, dst, *args, **kwargs):
        st = os.stat(src)
        captured[str(dst)] = [st.st_dev, st.st_ino]
        original_link(src, dst, *args, **kwargs)
        if str(dst) == str(out):
            out.unlink()
            out.write_bytes(b'competing writer')
    monkeypatch.setattr(os, 'link', replacing_link)
    result = backend().pivot(source, out)
    assert result['owned_artifacts'][str(out)] == captured[str(out)]
    st = out.stat()
    assert result['owned_artifacts'][str(out)] != [st.st_dev, st.st_ino]
    assert out.read_bytes() == b'competing writer'


def test_concurrent_output_file_is_preserved_on_publication_failure(tmp_path, monkeypatch):
    source, out = tmp_path/'source.glb', tmp_path/'pivot.glb'
    fixture(source)
    original_link = os.link
    def racing_link(src, dst, *args, **kwargs):
        if str(dst) == str(out):
            out.write_bytes(b'competing output')
        return original_link(src, dst, *args, **kwargs)
    monkeypatch.setattr(os, 'link', racing_link)
    with pytest.raises(FileExistsError):
        backend().pivot(source, out)
    assert out.read_bytes() == b'competing output'
    assert not out.with_suffix('.pivot-report.json').exists()


def test_report_race_rollback_does_not_remove_replaced_output(tmp_path, monkeypatch):
    source, out = tmp_path/'source.glb', tmp_path/'pivot.glb'
    fixture(source)
    original_link = os.link
    report = out.with_suffix('.pivot-report.json')
    def racing_link(src, dst, *args, **kwargs):
        if str(dst) == str(out):
            original_link(src, dst, *args, **kwargs)
            out.unlink()
            out.write_bytes(b'replacement output')
            return
        if str(dst) == str(report):
            report.write_bytes(b'competing report')
        return original_link(src, dst, *args, **kwargs)
    monkeypatch.setattr(os, 'link', racing_link)
    with pytest.raises(FileExistsError):
        backend().pivot(source, out)
    assert out.read_bytes() == b'replacement output'
    assert report.read_bytes() == b'competing report'
    assert not list(tmp_path.glob('.pivot-*'))


def test_report_hash_matches_exact_published_bytes_without_self_hash(tmp_path):
    source, out = tmp_path/'source.glb', tmp_path/'pivot.glb'
    fixture(source)
    result = backend().pivot(source, out)
    report_path = out.with_suffix('.pivot-report.json')
    assert result['report_sha256'] == hashlib.sha256(report_path.read_bytes()).hexdigest()
    assert 'report_sha256' not in result['report']
