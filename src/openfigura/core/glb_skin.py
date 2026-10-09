"""Strict, read-only GLB skin weight diagnostics using caller-defined families.

Scope is every node containing a skin, including nodes outside the active scene.
Instances are reported separately; no transforms, bind matrices, deformation or
collision tests are performed. Sparse and compressed attributes are unsupported.
"""
import hashlib
import math
import re
import struct

from .glb_faces import _read, _uint
from .skin_quality import analyze_weights


def _ref(items, index, label):
    index = _uint(index)
    if not isinstance(items, list) or index >= len(items):
        raise ValueError('invalid ' + label + ' reference')
    value = items[index]
    if not isinstance(value, dict):
        raise ValueError(label + ' must be an object')
    return value


def _attribute(doc, blob, index, semantic):
    accessor = _ref(doc.get('accessors'), index, 'accessor')
    if 'sparse' in accessor:
        raise ValueError('sparse skin attributes unsupported')
    component = accessor.get('componentType')
    if type(component) is not int:
        raise ValueError('componentType must be an integer enum')
    normalized = accessor.get('normalized', False)
    if type(normalized) is not bool:
        raise ValueError('normalized must be boolean')
    if semantic == 'POSITION':
        valid = component == 5126 and accessor.get('type') == 'VEC3' and not normalized
        width = 3
    elif semantic == 'JOINTS':
        valid = component in (5121, 5123) and accessor.get('type') == 'VEC4' and not normalized
        width = 4
    else:
        valid = (accessor.get('type') == 'VEC4' and
                 ((component == 5126 and not normalized) or
                  (component in (5121, 5123) and normalized)))
        width = 4
    if not valid:
        raise ValueError('unsupported ' + semantic + ' accessor type')
    code, size = {5121: ('B', 1), 5123: ('H', 2), 5126: ('f', 4)}[component]
    view = _ref(doc.get('bufferViews'), accessor['bufferView'], 'bufferView')
    if type(view.get('buffer')) is not int or view['buffer'] != 0:
        raise ValueError('attributes require embedded buffer zero')
    if 'EXT_meshopt_compression' in view.get('extensions', {}):
        raise ValueError('compressed skin attributes unsupported')
    count = _uint(accessor['count'])
    offset = _uint(view.get('byteOffset', 0))
    relative = _uint(accessor.get('byteOffset', 0))
    length = _uint(view['byteLength'])
    element = width * size
    stride = _uint(view.get('byteStride', element))
    start = offset + relative
    if (not count or stride < element or start % 4 or relative % size or
            offset % size or ('byteStride' in view and (stride % 4 or not 4 <= stride <= 252))):
        raise ValueError('invalid ' + semantic + ' attribute alignment or stride')
    if (offset + length > doc['buffers'][0]['byteLength'] or
            relative + (count - 1) * stride + element > length):
        raise ValueError(semantic + ' accessor outside buffer bounds')
    decoder = struct.Struct('<' + code * width)
    divisor = {5121: 255, 5123: 65535}.get(component, 1) if normalized else 1

    def values():
        for vertex in range(count):
            row = decoder.unpack_from(blob, start + vertex * stride)
            yield tuple(v / divisor for v in row) if normalized else row

    return count, values


def _rows(sets, names, count):
    iterators = [(joints(), weights()) for joints, weights in sets]
    for _ in range(count):
        influences = {}
        for joints, weights in iterators:
            for joint, weight in zip(next(joints), next(weights)):
                if joint >= len(names):
                    raise ValueError('joint local index outside skin joints')
                influences.setdefault(names[joint], []).append(weight)
        row = {}
        for name, weights in influences.items():
            # Do not let aggregation conceal a bad constituent through cancellation.
            if any(not math.isfinite(w) for w in weights):
                row[name] = float('-inf') if any(w < 0 for w in weights) else float('nan')
            elif any(w < 0 for w in weights):
                row[name] = min(weights)
            else:
                row[name] = math.fsum(weights)
        yield row


def analyze_glb_weights(path, families, pairs, **options):
    """Analyze all skin-bearing node primitives from one exact GLB snapshot.

    Supports glTF asset.version exactly 2.0, UINT8/UINT16 VEC4 joints,
    FLOAT32 or normalized UINT8/UINT16
    VEC4 weights and contiguous matching sets starting at zero. Structural
    errors raise ValueError; bad numeric weights remain diagnostic findings.
    Duplicate valid influences are summed without normalization. Invalid
    constituents remain invalid even if their duplicate influences cancel.
    """
    # Validate explicit semantic configuration even when no skin is present.
    analyze_weights([], families, pairs, **options)
    try:
        raw, doc, blob = _read(path)
        asset = doc.get('asset')
        if not isinstance(asset, dict) or asset.get('version') != '2.0':
            raise ValueError('glTF asset.version 2.0 required')
        if ('uri' in doc['buffers'][0] or
                len(blob) - doc['buffers'][0]['byteLength'] > 3):
            raise ValueError('one embedded buffer with at most three padding bytes required')
        reports = []
        nodes = doc.get('nodes', [])
        if not isinstance(nodes, list):
            raise ValueError('nodes must be an array')
        for node_id, node in enumerate(nodes):
            if not isinstance(node, dict):
                raise ValueError('node must be an object')
            if 'skin' not in node:
                continue
            if 'EXT_mesh_gpu_instancing' in node.get('extensions', {}):
                raise ValueError('GPU-instanced skin nodes unsupported')
            skin_id, mesh_id = _uint(node['skin']), _uint(node['mesh'])
            skin = _ref(doc.get('skins'), skin_id, 'skin')
            mesh = _ref(doc.get('meshes'), mesh_id, 'mesh')
            joints = skin['joints']
            if not isinstance(joints, list) or not joints:
                raise ValueError('skin must have a nonempty joint array')
            names = []
            for joint in joints:
                name = _ref(nodes, joint, 'joint node').get('name')
                if not isinstance(name, str) or not name or name in names:
                    raise ValueError('skin joint names must be unique and nonempty')
                names.append(name)
            primitives = mesh['primitives']
            if not isinstance(primitives, list) or not primitives:
                raise ValueError('skinned mesh must have primitives')
            for primitive_id, primitive in enumerate(primitives):
                if 'KHR_draco_mesh_compression' in primitive.get('extensions', {}):
                    raise ValueError('compressed skin primitives unsupported')
                attrs = primitive['attributes']
                if not isinstance(attrs, dict):
                    raise ValueError('attributes must be an object')
                count, _ = _attribute(doc, blob, attrs['POSITION'], 'POSITION')
                joint_sets, weight_sets = {}, {}
                for semantic, index in attrs.items():
                    if semantic.startswith(('JOINTS', 'WEIGHTS')):
                        match = re.fullmatch(r'(JOINTS|WEIGHTS)_(0|[1-9][0-9]*)', semantic)
                        if match is None:
                            raise ValueError('invalid skin attribute set name')
                        target = joint_sets if match[1] == 'JOINTS' else weight_sets
                        target[int(match[2])] = index
                if (not joint_sets or set(joint_sets) != set(weight_sets) or
                        sorted(joint_sets) != list(range(len(joint_sets)))):
                    raise ValueError('matching contiguous JOINTS/WEIGHTS sets required')
                sets = []
                for set_id in range(len(joint_sets)):
                    jc, jvalues = _attribute(doc, blob, joint_sets[set_id], 'JOINTS')
                    wc, wvalues = _attribute(doc, blob, weight_sets[set_id], 'WEIGHTS')
                    if jc != count or wc != count:
                        raise ValueError('skin attribute count must equal POSITION count')
                    sets.append((jvalues, wvalues))
                result = analyze_weights(_rows(sets, names, count), families, pairs, **options)
                reports.append({'node': node_id, 'skin': skin_id, 'mesh': mesh_id,
                                'primitive': primitive_id, **result})
    except (KeyError, IndexError, TypeError, AttributeError, struct.error) as exc:
        raise ValueError('invalid GLB skin structure: ' + str(exc)) from exc
    severity = {'unavailable': 0, 'no_flagged_conflicts': 1, 'suspicious': 2, 'invalid_weights': 3}
    assessment = max((r['assessment'] for r in reports), key=severity.get, default='unavailable')
    return {'assessment': assessment, 'vertices': sum(r['vertices'] for r in reports),
            'source_sha256': hashlib.sha256(raw).hexdigest(),
            'scope': 'all_skin_bearing_nodes', 'reports': reports,
            'skin_quality_accepted': False, 'collision_checked': False,
            'visual_approval': 'pending'}
