"""Static GLB origin translation, preserving all original attribute bytes.

This tool adds an identity asset root and a translation child; it does not bake vertices or move a pivot while
holding the asset at its previous world position. glTF coordinates are Y-up.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import tempfile
import time

from openfigura.core.glb_faces import _read, _indices, _uint


# These extensions only affect material interpretation, not scene geometry.
_MATERIAL_EXTENSIONS = frozenset({
    'KHR_materials_unlit', 'KHR_materials_ior', 'KHR_materials_emissive_strength',
    'KHR_materials_clearcoat', 'KHR_materials_transmission', 'KHR_materials_volume',
    'KHR_materials_specular', 'KHR_materials_sheen', 'KHR_materials_iridescence',
    'KHR_materials_anisotropy', 'KHR_materials_pbrSpecularGlossiness',
    'KHR_materials_dispersion', 'KHR_texture_transform',
})
_IDENTITY = [1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.]


def _vector(value, size, label):
    if (not isinstance(value, list) or len(value) != size or
            any(type(v) not in (int, float) or not math.isfinite(v) for v in value)):
        raise ValueError(f'{label} must contain {size} finite numbers')
    return value


def _item(items, index, label):
    index = _uint(index)
    if index >= len(items):
        raise ValueError(f'invalid {label} index')
    return items[index]


def _multiply(a, b):
    result = [sum(a[k*4+r] * b[c*4+k] for k in range(4)) for c in range(4) for r in range(4)]
    if not all(math.isfinite(v) for v in result):
        raise ValueError('nonfinite composed transform')
    return result


def _transform(node):
    if node.get('extensions'):
        raise ValueError('node extensions (including instancing) unsupported')
    if 'matrix' in node:
        if any(key in node for key in ('translation', 'rotation', 'scale')):
            raise ValueError('node matrix and TRS are mutually exclusive')
        matrix = _vector(node['matrix'], 16, 'matrix')
        if [matrix[i] for i in (3, 7, 11, 15)] != [0, 0, 0, 1]:
            raise ValueError('node matrix must be affine')
        return matrix
    t = _vector(node.get('translation', [0., 0., 0.]), 3, 'translation')
    s = _vector(node.get('scale', [1., 1., 1.]), 3, 'scale')
    x, y, z, w = _vector(node.get('rotation', [0., 0., 0., 1.]), 4, 'rotation')
    norm = x*x+y*y+z*z+w*w
    if not math.isfinite(norm) or abs(norm-1.) > 1e-5:
        raise ValueError('rotation quaternion must have unit length')
    # glTF column-major T*R*S, including negative scale.
    return [
        (1-2*(y*y+z*z))*s[0], 2*(x*y+z*w)*s[0], 2*(x*z-y*w)*s[0], 0.,
        2*(x*y-z*w)*s[1], (1-2*(x*x+z*z))*s[1], 2*(y*z+x*w)*s[1], 0.,
        2*(x*z+y*w)*s[2], 2*(y*z-x*w)*s[2], (1-2*(x*x+y*y))*s[2], 0.,
        *t, 1.,
    ]


def _position_layout(doc, blob, primitive):
    accessor = _item(doc['accessors'], primitive['attributes']['POSITION'], 'POSITION accessor')
    if (accessor.get('componentType') != 5126 or accessor.get('type') != 'VEC3' or
            'sparse' in accessor or accessor.get('normalized') or accessor.get('extensions')):
        raise ValueError('POSITION requires plain nonsparse FLOAT VEC3')
    view = _item(doc['bufferViews'], accessor['bufferView'], 'POSITION bufferView')
    if view.get('buffer', 0) != 0 or view.get('extensions'):
        raise ValueError('compressed/external POSITION buffer unsupported')
    count = _uint(accessor['count'])
    relative = _uint(accessor.get('byteOffset', 0))
    offset = _uint(view.get('byteOffset', 0))
    length = _uint(view['byteLength'])
    stride = _uint(view.get('byteStride', 12))
    if (not count or stride < 12 or stride > 252 or stride % 4 or
            relative % 4 or offset % 4):
        raise ValueError('invalid POSITION layout')
    if (offset+length > doc['buffers'][0]['byteLength'] or
            relative+(count-1)*stride+12 > length):
        raise ValueError('POSITION accessor outside buffer bounds')
    # Bounds metadata is deliberately ignored. Validate every decoded vertex,
    # even if a malformed mesh fails to reference the nonfinite vertex.
    for i in range(count):
        if not all(math.isfinite(v) for v in struct.unpack_from('<fff', blob, offset+relative+i*stride)):
            raise ValueError('nonfinite POSITION value')
    return offset+relative, stride


def _bounds(doc, blob):
    if doc.get('asset', {}).get('version') != '2.0':
        raise ValueError('glTF 2.0 required')
    if doc.get('skins') or doc.get('animations'):
        raise ValueError('only static assets without skins/animations supported')
    if set(doc.get('extensionsRequired', [])) - _MATERIAL_EXTENSIONS or doc.get('extensions'):
        raise ValueError('unsupported required or root geometry extensions')
    for image in doc.get('images', []):
        if 'uri' in image and (not isinstance(image['uri'], str) or not image['uri'].startswith('data:')):
            raise ValueError('external image sidecars unsupported; embedded images required')
    scenes = doc.get('scenes', [])
    if len(scenes) != 1 or type(doc.get('scene', 0)) is not int or doc.get('scene', 0) != 0:
        raise ValueError('exactly one default scene required')
    scene = scenes[0]
    if scene.get('extensions'):
        raise ValueError('scene extensions unsupported')
    nodes = doc.get('nodes', [])
    roots = scene.get('nodes', [])
    if not isinstance(roots, list) or not roots:
        raise ValueError('default scene must have roots')
    parents = {}
    transforms = []
    for index, node in enumerate(nodes):
        if 'skin' in node or 'weights' in node:
            raise ValueError('skin/morph nodes unsupported')
        transforms.append(_transform(node))
        children = node.get('children', [])
        if not isinstance(children, list):
            raise ValueError('children must be a list')
        for child in children:
            _item(nodes, child, 'child node')
            if child in parents:
                raise ValueError('node has multiple parents or duplicate child references')
            parents[child] = index
    root_set = set()
    for root in roots:
        _item(nodes, root, 'scene root')
        if root in root_set or root in parents:
            raise ValueError('scene roots must be unique parentless nodes')
        root_set.add(root)
    # Validate even unreachable branches; iterative traversal avoids recursion
    # failure on deep valid hierarchies and rejects cycles independently.
    done = set()
    for index in range(len(nodes)):
        chain = set()
        cursor = index
        while cursor not in done:
            if cursor in chain:
                raise ValueError('node hierarchy contains a cycle')
            chain.add(cursor)
            if cursor not in parents:
                break
            cursor = parents[cursor]
        done.update(chain)
    geometries = []
    for mesh in doc.get('meshes', []):
        if 'weights' in mesh or mesh.get('extensions'):
            raise ValueError('morph/extended meshes unsupported')
        primitives = mesh.get('primitives', [])
        if not primitives:
            raise ValueError('empty mesh unsupported')
        entries = []
        for primitive in primitives:
            if primitive.get('targets') or primitive.get('extensions'):
                raise ValueError('morph/compressed/extended primitives unsupported')
            start, stride = _position_layout(doc, blob, primitive)
            index_accessor = _item(doc['accessors'], primitive['indices'], 'index accessor')
            if index_accessor.get('extensions') or index_accessor.get('normalized'):
                raise ValueError('extended/normalized index accessor unsupported')
            index_view = _item(doc['bufferViews'], index_accessor['bufferView'], 'index bufferView')
            if index_view.get('extensions'):
                raise ValueError('extended index buffer unsupported')
            if 'byteStride' in index_view:
                raise ValueError('index bufferView must not declare byteStride')
            indices = _indices(doc, blob, primitive)
            entries.append((start, stride, set(indices)))
        geometries.append(entries)
    minimum, maximum = [math.inf]*3, [-math.inf]*3
    stack = [(root, _IDENTITY) for root in roots]
    while stack:
        index, parent = stack.pop()
        node = nodes[index]
        world = _multiply(parent, transforms[index])
        if 'mesh' in node:
            entries = _item(geometries, node['mesh'], 'mesh')
            for start, stride, indices in entries:
                for vertex in indices:
                    point = struct.unpack_from('<fff', blob, start+vertex*stride)
                    transformed = [sum(world[c*4+r]*point[c] for c in range(3))+world[12+r] for r in range(3)]
                    if not all(math.isfinite(v) for v in transformed):
                        raise ValueError('nonfinite world POSITION')
                    for axis in range(3):
                        minimum[axis] = min(minimum[axis], transformed[axis])
                        maximum[axis] = max(maximum[axis], transformed[axis])
        stack.extend((child, world) for child in node.get('children', []))
    if not all(math.isfinite(v) for v in minimum+maximum):
        raise ValueError('default scene has no triangle geometry')
    return {'min': minimum, 'max': maximum}


def _publish(payload, report_data, output, report_path):
    """Stage both files, then link without replacing an existing destination."""
    output.parent.mkdir(parents=True, exist_ok=True)
    temporaries = []
    owners = []
    published = []
    try:
        for data, destination in ((payload, output), (report_data, report_path)):
            with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.pivot-', delete=False) as handle:
                temporary = Path(handle.name)
                temporaries.append(temporary)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
                owners.append(os.fstat(handle.fileno()))
        for temporary, destination, owner in zip(temporaries, (output, report_path), owners):
            os.link(temporary, destination, follow_symlinks=False)
            published.append((destination, owner))
    except BaseException:
        # Do not remove a competing writer's output or dangling symlink.
        for destination, owner in reversed(published):
            try:
                current = destination.lstat()
                if (current.st_dev, current.st_ino) == (owner.st_dev, owner.st_ino):
                    destination.unlink()
            except FileNotFoundError:
                pass
        raise
    finally:
        for temporary in temporaries:
            temporary.unlink(missing_ok=True)
    return {str(destination): [owner.st_dev, owner.st_ino] for destination, owner in published}


class PivotBackend:
    id = 'gltf-pivot'
    kind = 'postprocess'

    def capabilities(self):
        # Late import: registry bootstrap may import this module.
        from openfigura.core.registry import Capabilities
        return Capabilities(available=True, hardware='cpu', notes={
            'method': 'stdlib GLB identity asset root with translated geometry child; glTF Y-up',
            'modes': 'ground: horizontal center at ground; center: bounds center at origin',
            'limits': 'one embedded static GLB scene; indexed uncompressed triangles; FLOAT VEC3 POSITION; no skin/morph/animation/instancing',
            'preservation': 'all original nodes and BIN bytes preserved; translates world geometry, not a fixed-position mesh pivot',
        })

    def pivot(self, model: Path, output: Path, mode: str = 'ground') -> dict:
        started = time.monotonic()
        if mode not in ('ground', 'center'):
            raise ValueError('mode must be ground or center')
        source = Path(model).resolve()
        output = Path(output).absolute()
        report_path = output.with_suffix('.pivot-report.json')
        for destination in (output, report_path):
            if destination.resolve() == source or destination.exists() or destination.is_symlink():
                raise FileExistsError('refusing to overwrite source or existing output/report')
        try:
            raw, original, blob = _read(source)
            before = _bounds(original, blob)
            center = [before['min'][i]/2.+before['max'][i]/2. for i in range(3)]
            translation = [-center[0], -before['min'][1] if mode == 'ground' else -center[1], -center[2]]
            after = {key: [before[key][i]+translation[i] for i in range(3)] for key in ('min', 'max')}
            doc = deepcopy(original)
            offset_node = len(doc['nodes'])
            doc['nodes'].append({'name': 'OpenFiguraPivotOffset', 'translation': translation,
                                 'children': list(doc['scenes'][0]['nodes'])})
            asset_root_node = len(doc['nodes'])
            doc['nodes'].append({'name': 'OpenFiguraPivot', 'children': [offset_node]})
            doc['scenes'][0]['nodes'] = [asset_root_node]
            encoded = json.dumps(doc, separators=(',', ':'), allow_nan=False).encode('utf-8')
            encoded += b' ' * (-len(encoded) % 4)
            payload = (struct.pack('<III', 0x46546C67, 2, 28+len(encoded)+len(blob)) +
                       struct.pack('<II', len(encoded), 0x4E4F534A)+encoded +
                       struct.pack('<II', len(blob), 0x004E4942)+blob)
        except (KeyError, IndexError, TypeError, AttributeError, OverflowError, struct.error) as exc:
            raise ValueError(f'invalid or unsupported static GLB: {exc}') from exc
        source_hash, output_hash = hashlib.sha256(raw).hexdigest(), hashlib.sha256(payload).hexdigest()
        report = {'mode': mode, 'bounds_before': before, 'bounds_after': after,
                  'world_translation': translation, 'coordinate_system': 'glTF Y-up',
                  'asset_root_node': asset_root_node, 'pivot_world_origin': [0., 0., 0.],
                  'attribute_bytes_preserved': True, 'original_nodes_preserved': True,
                  'original_bin_sha256': hashlib.sha256(blob).hexdigest(),
                  'source_sha256': source_hash, 'output_sha256': output_hash,
                  'bounds_scope': 'referenced triangle POSITION vertices in the default scene',
                  'semantics': 'asset origin/world geometry translation; previous world position is not retained',
                  'visual_approval': 'pending'}
        report_data = json.dumps(report, indent=2, allow_nan=False).encode('utf-8')+b'\n'
        report_hash = hashlib.sha256(report_data).hexdigest()
        owned_artifacts = _publish(payload, report_data, output, report_path)
        return {'backend': self.id, 'status': 'ok', 'exit_code': 0, 'produced': True,
                'device': 'cpu', 'wall_seconds': time.monotonic()-started,
                'owned_artifacts': owned_artifacts, 'report_sha256': report_hash,
                'source_sha256': source_hash, 'output_sha256': output_hash,
                'output': str(output), 'output_path': str(output),
                'report_path': str(report_path), 'report': report}
