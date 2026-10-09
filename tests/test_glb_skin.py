"""Real GLB fixtures exercise parsing, skin mapping and diagnostic scope."""
import hashlib
import json
import struct
from copy import deepcopy

import pytest

FAMILIES = {'hand': ['finger'], 'leg': ['thigh']}
PAIRS = [('hand', 'leg')]


def analyze(path, **kwargs):
    from openfigura.core.glb_skin import analyze_glb_weights
    return analyze_glb_weights(path, FAMILIES, PAIRS, **kwargs)


def fixture(*, joints_type=5121, weights_type=5126, normalized=False,
            sets=None, count=1, stride=False):
    doc = {'asset': {'version': '2.0'}, 'buffers': [], 'bufferViews': [],
           'accessors': [], 'nodes': [{'name': 'finger'}, {'name': 'thigh'},
                                    {'mesh': 0, 'skin': 0}],
           'skins': [{'joints': [0, 1]}], 'meshes': [{'primitives': []}]}
    blob = bytearray()

    def accessor(values, component, shape, normalized=False):
        code, size = {5121: ('B', 1), 5123: ('H', 2), 5126: ('f', 4)}[component]
        width = {'VEC3': 3, 'VEC4': 4}[shape]
        blob.extend(b'\0' * ((-len(blob)) % 4))
        offset = len(blob)
        element = width * size
        step = element + 4 if stride else element
        for row in values:
            blob.extend(struct.pack('<' + code * width, *row))
            if stride:
                blob.extend(b'\0' * 4)
        view = {'buffer': 0, 'byteOffset': offset, 'byteLength': len(blob) - offset}
        if stride:
            view['byteStride'] = step
        doc['bufferViews'].append(view)
        acc = {'bufferView': len(doc['bufferViews']) - 1, 'componentType': component,
               'type': shape, 'count': len(values)}
        if normalized:
            acc['normalized'] = True
        doc['accessors'].append(acc)
        return len(doc['accessors']) - 1

    attributes = {'POSITION': accessor([(0, 0, 0)] * count, 5126, 'VEC3')}
    if sets is None:
        scale = {5121: 255, 5123: 65535, 5126: 1}[weights_type]
        sets = [([(0, 1, 0, 0)] * count, [(scale, 0, 0, 0)] * count)]
    for i, (joints, weights) in enumerate(sets):
        attributes['JOINTS_' + str(i)] = accessor(joints, joints_type, 'VEC4')
        attributes['WEIGHTS_' + str(i)] = accessor(weights, weights_type, 'VEC4', normalized)
    doc['meshes'][0]['primitives'].append({'attributes': attributes})
    doc['buffers'] = [{'byteLength': len(blob)}]
    return doc, blob


def write(tmp_path, doc, blob):
    encoded = json.dumps(doc, separators=(',', ':')).encode()
    encoded += b' ' * ((-len(encoded)) % 4)
    padded = bytes(blob) + b'\0' * ((-len(blob)) % 4)
    raw = (struct.pack('<III', 0x46546c67, 2, 28 + len(encoded) + len(padded)) +
           struct.pack('<II', len(encoded), 0x4e4f534a) + encoded +
           struct.pack('<II', len(padded), 0x004e4942) + padded)
    path = tmp_path / 'input.glb'
    path.write_bytes(raw)
    return path


def test_report_hash_scope_and_flags(tmp_path):
    doc, blob = fixture(count=2)
    path = write(tmp_path, doc, blob)
    raw = path.read_bytes()
    report = analyze(path)
    assert report['assessment'] == 'no_flagged_conflicts'
    assert report['vertices'] == 2
    assert report['source_sha256'] == hashlib.sha256(raw).hexdigest()
    assert report['scope'] == 'all_skin_bearing_nodes'
    assert report['skin_quality_accepted'] is False
    assert report['collision_checked'] is False
    assert report['visual_approval'] == 'pending'
    assert {k: report['reports'][0][k] for k in ('node', 'skin', 'mesh', 'primitive')} == {
        'node': 2, 'skin': 0, 'mesh': 0, 'primitive': 0}
    assert path.read_bytes() == raw


@pytest.mark.parametrize('joints_type', [5121, 5123])
@pytest.mark.parametrize('weights_type', [5121, 5123, 5126])
def test_supported_components_and_interleaved_stride(tmp_path, joints_type, weights_type):
    doc, blob = fixture(joints_type=joints_type, weights_type=weights_type,
                        normalized=weights_type != 5126, stride=True)
    assert analyze(write(tmp_path, doc, blob))['assessment'] == 'no_flagged_conflicts'


def test_multiple_sets_duplicate_influences_aggregate(tmp_path):
    doc, blob = fixture(sets=[([(0, 1, 0, 0)], [(.2, .3, 0, 0)]),
                             ([(0, 1, 0, 0)], [(.3, .2, 0, 0)])])
    report = analyze(write(tmp_path, doc, blob))['reports'][0]
    assert report['assessment'] == 'suspicious'
    sample = report['conflicts'][0]['samples'][0]
    assert sample['mass_a'] == pytest.approx(.5)
    assert sample['mass_b'] == pytest.approx(.5)


def test_all_skin_nodes_use_their_own_joint_mapping_and_all_primitives(tmp_path):
    doc, blob = fixture(sets=[([(0, 1, 0, 0)], [(1, 0, 0, 0)])])
    doc['nodes'].extend([{'name': 'outside'}, {'mesh': 0, 'skin': 1}])
    doc['skins'].append({'joints': [3, 1]})
    doc['meshes'][0]['primitives'].append(deepcopy(doc['meshes'][0]['primitives'][0]))
    report = analyze(write(tmp_path, doc, blob))
    assert report['vertices'] == 4
    assert len(report['reports']) == 4
    assert [r['unmapped_bone_names'] for r in report['reports']] == [[], [], ['outside'], ['outside']]


@pytest.mark.parametrize('weight, counter', [(float('nan'), 'nonfinite_weight_vertices'),
    (float('inf'), 'nonfinite_weight_vertices'), (-.1, 'negative_weight_vertices'),
    (.7, 'weight_sum_outside_tolerance_vertices'), (0, 'unweighted_vertices')])
def test_bad_numeric_weights_are_diagnosed(tmp_path, weight, counter):
    doc, blob = fixture(sets=[([(0, 1, 0, 0)], [(weight, 0, 0, 0)])])
    report = analyze(write(tmp_path, doc, blob))
    assert report['assessment'] == 'invalid_weights'
    assert report['reports'][0][counter] == 1


def test_no_skin_nodes_is_unavailable(tmp_path):
    doc, blob = fixture()
    del doc['nodes'][2]['skin']
    report = analyze(write(tmp_path, doc, blob))
    assert report['assessment'] == 'unavailable'
    assert report['reports'] == []
    assert report['vertices'] == 0


@pytest.mark.parametrize('mutation', [
    lambda d: d['nodes'][2].update(skin=-1),
    lambda d: d['nodes'][2].update(skin=10),
    lambda d: d['nodes'][2].update(mesh=10),
    lambda d: d['nodes'][2].pop('mesh'),
    lambda d: d['skins'][0].update(joints=[0, 0]),
    lambda d: d['skins'][0].update(joints=[0, 20]),
    lambda d: d['nodes'][1].update(name='finger'),
    lambda d: d['nodes'][0].pop('name'),
    lambda d: d['meshes'][0]['primitives'][0]['attributes'].pop('JOINTS_0'),
    lambda d: d['meshes'][0]['primitives'][0]['attributes'].update(JOINTS_2=1, WEIGHTS_2=2),
    lambda d: d['meshes'][0]['primitives'][0]['attributes'].update(JOINTS_bad=1),
    lambda d: d['meshes'][0]['primitives'][0]['attributes'].update(WEIGHTS_1=2),
    lambda d: d['accessors'][1].update(count=2),
    lambda d: d['accessors'][1].update(sparse={}),
    lambda d: d['accessors'][1].update(componentType=5125),
    lambda d: d['accessors'][1].update(type='VEC3'),
    lambda d: d['accessors'][1].update(normalized=True),
    lambda d: d['accessors'][2].update(componentType=5121),
    lambda d: d['accessors'][2].update(normalized=True),
    lambda d: d['accessors'][2].update(bufferView=-1),
    lambda d: d['accessors'][2].update(bufferView=20),
    lambda d: d['accessors'][2].update(byteOffset=2),
    lambda d: d['bufferViews'][2].update(buffer=1),
    lambda d: d['bufferViews'][2].update(byteLength=12),
    lambda d: d['bufferViews'][2].update(byteOffset=999),
    lambda d: d['bufferViews'][2].update(byteStride=8),
    lambda d: d['bufferViews'][2].update(byteStride=18),
    lambda d: d['bufferViews'][2].update(byteStride=256),
    lambda d: d['bufferViews'][2].update(extensions={'EXT_meshopt_compression': {}}),
    lambda d: d['meshes'][0]['primitives'][0].update(extensions={'KHR_draco_mesh_compression': {}}),
])
def test_malformed_and_unsupported_glb_is_rejected(tmp_path, mutation):
    doc, blob = fixture()
    mutation(doc)
    with pytest.raises(ValueError):
        analyze(write(tmp_path, doc, blob))


def test_joint_index_out_of_skin_is_rejected_even_with_zero_weight(tmp_path):
    doc, blob = fixture(sets=[([(0, 1, 2, 0)], [(1, 0, 0, 0)])])
    with pytest.raises(ValueError):
        analyze(write(tmp_path, doc, blob))


def test_bad_container_is_rejected(tmp_path):
    path = tmp_path / 'bad.glb'
    path.write_bytes(b'invalid')
    with pytest.raises(ValueError):
        analyze(path)


def test_configuration_is_validated_without_skin_nodes(tmp_path):
    from openfigura.core.glb_skin import analyze_glb_weights
    doc, blob = fixture()
    doc['nodes'] = doc['nodes'][:2]
    with pytest.raises(ValueError):
        analyze_glb_weights(write(tmp_path, doc, blob), {}, PAIRS)


@pytest.mark.parametrize('mutation', [
    lambda d: d['buffers'][0].update(uri=''),
    lambda d: d['buffers'][0].update(byteLength=d['buffers'][0]['byteLength'] - 4),
    lambda d: d['meshes'][0]['primitives'][0]['attributes'].update(JOINTS=1),
    lambda d: d['nodes'][2].update(extensions={'EXT_mesh_gpu_instancing': {}}),
])
def test_external_buffers_extra_bin_and_unsupported_instancing_rejected(tmp_path, mutation):
    doc, blob = fixture()
    mutation(doc)
    with pytest.raises(ValueError):
        analyze(write(tmp_path, doc, blob))


def test_bin_padding_is_at_most_three_bytes_even_when_unskinned(tmp_path):
    doc, blob = fixture()
    doc['nodes'] = doc['nodes'][:2]
    doc['buffers'][0]['byteLength'] -= 4
    with pytest.raises(ValueError):
        analyze(write(tmp_path, doc, blob))


@pytest.mark.parametrize('weights', [(-float('inf'), 0, 0, 0),
                                    (float('nan'), 0, -.1, 0)])
def test_nonfinite_and_negative_duplicate_influences_preserve_both_diagnostics(tmp_path, weights):
    doc, blob = fixture(sets=[([(0, 1, 0, 0)], [weights])])
    report = analyze(write(tmp_path, doc, blob))['reports'][0]
    assert report['negative_weight_vertices'] == 1
    assert report['nonfinite_weight_vertices'] == 1
    assert report['conflict_checked_vertices'] == 0


@pytest.mark.parametrize('mutation', [
    lambda d: d['accessors'][0].update(componentType=5126.0),
    lambda d: d['accessors'][1].update(componentType=5121.0),
    lambda d: d['accessors'][2].update(componentType=5126.0),
    lambda d: d.pop('asset'),
    lambda d: d.update(asset=[]),
    lambda d: d.update(asset=None),
    lambda d: d['asset'].pop('version'),
    lambda d: d['asset'].update(version='1.0'),
    lambda d: d['asset'].update(version='2.1'),
    lambda d: d['asset'].update(version=2.0),
])
def test_strict_component_enum_and_supported_asset_version(tmp_path, mutation):
    doc, blob = fixture()
    mutation(doc)
    with pytest.raises(ValueError):
        analyze(write(tmp_path, doc, blob))
