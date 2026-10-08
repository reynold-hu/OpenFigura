"""Delete selected triangles without re-encoding GLB attributes or materials.

This is an index editor, not a repair verdict. The caller must supply a
verified original-face mask and independently assess removed surfaces.
"""
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import tempfile


def _uint(value):
    if type(value) is not int or value < 0:
        raise ValueError('index, offset and count must be nonnegative integers')
    return value


def _read(path):
    data = Path(path).read_bytes()
    if len(data) < 28 or struct.unpack_from('<III', data) != (0x46546C67, 2, len(data)):
        raise ValueError('invalid GLB container')
    chunks = []; offset = 12
    while offset < len(data):
        if offset+8 > len(data): raise ValueError('truncated GLB chunk')
        length, kind = struct.unpack_from('<II', data, offset)
        if length % 4 or offset+8+length > len(data): raise ValueError('invalid GLB chunk length')
        chunks.append((kind, data[offset+8:offset+8+length])); offset += 8+length
    if [kind for kind, _ in chunks] != [0x4E4F534A, 0x004E4942]:
        raise ValueError('expected one JSON and one BIN chunk')
    doc = json.loads(chunks[0][1]); blob = chunks[1][1]
    buffers = doc.get('buffers', [])
    if len(buffers) != 1 or buffers[0].get('uri') or _uint(buffers[0]['byteLength']) > len(blob):
        raise ValueError('one embedded buffer required')
    return data, doc, blob


def _indices(doc, blob, primitive):
    if primitive.get('mode', 4) != 4 or 'KHR_draco_mesh_compression' in primitive.get('extensions', {}):
        raise ValueError('only indexed uncompressed triangles supported')
    accessor = doc['accessors'][_uint(primitive['indices'])]
    if accessor.get('type') != 'SCALAR' or 'sparse' in accessor:
        raise ValueError('only nonsparse scalar index accessors supported')
    code, size = {5121:('B',1),5123:('H',2),5125:('I',4)}.get(accessor.get('componentType'), (None, 0))
    if code is None: raise ValueError('unsupported triangle index type')
    view = doc['bufferViews'][_uint(accessor['bufferView'])]
    if view.get('buffer', 0) != 0 or 'EXT_meshopt_compression' in view.get('extensions', {}):
        raise ValueError('compressed/external index buffers unsupported')
    count = _uint(accessor['count']); relative = _uint(accessor.get('byteOffset',0))
    offset = _uint(view.get('byteOffset',0)); length = _uint(view['byteLength'])
    stride = _uint(view.get('byteStride',size)); start = offset+relative
    if not count or count % 3 or stride < size or start % size:
        raise ValueError('invalid triangle index layout')
    if offset+length > doc['buffers'][0]['byteLength'] or relative+(count-1)*stride+size > length:
        raise ValueError('index accessor outside buffer bounds')
    values = [struct.unpack_from('<'+code,blob,start+i*stride)[0] for i in range(count)]
    vertices = _uint(doc['accessors'][_uint(primitive['attributes']['POSITION'])]['count'])
    if any(i >= vertices for i in values): raise ValueError('triangle vertex index outside POSITION')
    return values


def prune_faces(source, output, keep_faces, *, max_removed_fraction=.01):
    """Keep original triangle IDs per (mesh, primitive), retain all other data.

    Original BIN bytes/accessors/views are untouched; new index data is appended.
    Empty primitives, ambiguous masks and overwrite requests are refused.
    """
    source, output = Path(source).resolve(), Path(output).absolute()
    if source == output.resolve(): raise ValueError('refusing to overwrite source')
    if output.exists() or output.is_symlink(): raise FileExistsError('output already exists')
    if type(max_removed_fraction) not in (int,float) or not math.isfinite(max_removed_fraction) or not 0 <= max_removed_fraction < 1:
        raise ValueError('max_removed_fraction must be finite in [0,1)')
    if not isinstance(keep_faces, dict) or not keep_faces: raise ValueError('face masks required')
    raw, original, original_blob = _read(source)
    if original.get('skins') or original.get('animations'):
        raise ValueError('index repair is limited to static assets')
    doc = deepcopy(original); blob = bytearray(original_blob); records = []
    before = removed = 0
    for key, keep in keep_faces.items():
        try:
            if not isinstance(key, tuple) or len(key) != 2: raise ValueError('mask key must be (mesh, primitive)')
            mesh, prim = map(_uint,key); primitive = doc['meshes'][mesh]['primitives'][prim]
            if primitive.get('targets'): raise ValueError('morph targets unsupported')
            indices = _indices(doc, original_blob, primitive); faces = len(indices)//3
            if not isinstance(keep,(list,tuple)) or not keep or any(type(i) is not int or not 0 <= i < faces for i in keep):
                raise ValueError('mask requires valid nonempty original triangle IDs')
            if len(set(keep)) != len(keep): raise ValueError('duplicate triangle IDs in mask')
            keep = sorted(keep); deleted = faces-len(keep)
            if deleted/faces > max_removed_fraction: raise ValueError('face removal budget exceeded')
            selected = [v for face in keep for v in indices[3*face:3*face+3]]
            new_data = struct.pack('<'+'I'*len(selected),*selected)
            view = len(doc['bufferViews']); accessor = len(doc['accessors'])
            doc['bufferViews'].append({'buffer':0,'byteOffset':len(blob),'byteLength':len(new_data),'target':34963})
            blob.extend(new_data)
            doc['accessors'].append({'bufferView':view,'componentType':5125,'type':'SCALAR','count':len(selected),
                                     'min':[min(selected)],'max':[max(selected)]})
            primitive['indices'] = accessor
            records.append({'mesh':mesh,'primitive':prim,'before_faces':faces,'after_faces':len(keep),'removed_faces':deleted})
            before += faces; removed += deleted
        except (KeyError,IndexError,TypeError) as exc:
            raise ValueError('invalid source primitive or mask: '+str(exc)) from exc
    doc['buffers'][0]['byteLength'] = len(blob)
    encoded = json.dumps(doc, separators=(',',':'), allow_nan=False).encode()
    encoded += b' '*((-len(encoded))%4)
    payload = (struct.pack('<III',0x46546C67,2,28+len(encoded)+len(blob))+
               struct.pack('<II',len(encoded),0x4E4F534A)+encoded+
               struct.pack('<II',len(blob),0x004E4942)+blob)
    output.parent.mkdir(parents=True,exist_ok=True)
    # Atomic publication without replacing a concurrently created output.
    with tempfile.NamedTemporaryFile(dir=output.parent,delete=False) as handle:
        temporary = Path(handle.name)
        try: handle.write(payload)
        except BaseException: temporary.unlink(missing_ok=True); raise
    try: os.link(temporary,output)
    finally: temporary.unlink(missing_ok=True)
    return {'source_sha256':hashlib.sha256(raw).hexdigest(),'output_sha256':hashlib.sha256(payload).hexdigest(),
            'removed_faces':removed,'before_faces':before,'face_count_scope':'edited_primitives_only','primitives':records,
            'attribute_bytes_preserved':True,'original_bin_prefix_sha256':hashlib.sha256(original_blob).hexdigest(),
            'repair_complete':False,'visual_approval':'pending'}
