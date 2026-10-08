"""Blender-only worker. Original implementation; no third-party copied scripts."""
import json
import hashlib
from collections import Counter
import math
import sys
import struct
from pathlib import Path

import bpy
import bmesh
from mathutils.bvhtree import BVHTree


def meshes():
    return [o for o in bpy.context.scene.objects if o.type == 'MESH' and not o.hide_render and o.visible_get()]


def activate(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def bounding_box(obj):
    corners = list(obj.bound_box)
    return tuple(max(c[i] for c in corners) - min(c[i] for c in corners) for i in range(3))


def stats(objects):
    for obj in objects:
        obj.data.calc_loop_triangles()
    return {'objects': len(objects), 'vertices': sum(len(o.data.vertices) for o in objects),
            'triangles': sum(len(o.data.loop_triangles) for o in objects),
            'quads': sum(sum(len(p.vertices) == 4 for p in o.data.polygons) for o in objects),
            'materials': sorted({m.name for o in objects for m in o.data.materials if m}),
            'uv_layers': {o.name: len(o.data.uv_layers) for o in objects}}


def component_groups(mesh):
    neighbors = [[] for _ in mesh.vertices]
    for edge in mesh.edges:
        a, b = edge.vertices; neighbors[a].append(b); neighbors[b].append(a)
    positions = {}
    for index, vertex in enumerate(mesh.vertices):
        key = tuple(vertex.co)
        if key in positions:
            other = positions[key]; neighbors[index].append(other); neighbors[other].append(index)
        else:
            positions[key] = index
    visited = set(); groups = []
    for vertex in range(len(neighbors)):
        if vertex in visited:
            continue
        group = []; stack = [vertex]; visited.add(vertex)
        while stack:
            current = stack.pop(); group.append(current)
            for other in neighbors[current]:
                if other not in visited:
                    visited.add(other); stack.append(other)
        groups.append(group)
    return groups


def glb_nonfinite_metrics(path):
    """Check encoded position/UV floats before Blender can sanitize them.

    Embedded GLB float accessors (including sparse values) are inspected;
    compressed attributes and external buffer layouts are refused explicitly.
    Sparse base and override values are both checked, without hiding illegal
    encoded values that an override could otherwise mask.
    """
    data = Path(path).read_bytes()
    try:
        magic, version, length = struct.unpack_from('<III', data)
        if magic != 0x46546C67 or version != 2 or length != len(data):
            raise ValueError('invalid GLB container')
        document = None; binary = None; offset = 12; chunks = 0
        while offset < length:
            size, kind = struct.unpack_from('<II', data, offset)
            end = offset+8+size
            expected = (0x4E4F534A, 0x004E4942)
            if chunks >= 2 or kind != expected[chunks] or size % 4:
                raise ValueError('unsupported GLB chunk layout: requires one JSON followed by one BIN; duplicate/unknown chunks refused')
            chunks += 1
            if end > length:
                raise ValueError('truncated GLB chunk')
            if kind == 0x4E4F534A:
                document = json.loads(data[offset+8:end])
            elif kind == 0x004E4942:
                binary = memoryview(data)[offset+8:end]
            offset = end
        if document is None or binary is None:
            raise ValueError('GLB numeric preflight requires JSON and embedded BIN')
        def integer(value):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError('numeric accessor index/offset/count must be a nonnegative integer')
            return value
        if len(document['buffers']) != 1 or document['buffers'][0].get('uri'):
            raise ValueError('external/multiple buffers unsupported by numeric preflight')
        if any('EXT_meshopt_compression' in view.get('extensions', {}) for view in document.get('bufferViews', [])):
            raise ValueError('compressed buffer view unsupported by numeric preflight')
        buffer_length = integer(document['buffers'][0]['byteLength'])
        if buffer_length > len(binary):
            raise ValueError('embedded buffer exceeds BIN bounds')
        metrics = {'nonfinite_positions': 0, 'nonfinite_uv_corners': 0,
                   'coverage': 'embedded POSITION/TEXCOORD floats, including sparse base and values; compressed/external attributes refused'}
        seen = set()
        for mesh in document.get('meshes', []):
            for primitive in mesh.get('primitives', []):
                if 'KHR_draco_mesh_compression' in primitive.get('extensions', {}):
                    raise ValueError('compressed attributes unsupported by numeric preflight')
                for semantic, index in primitive.get('attributes', {}).items():
                    key = 'nonfinite_positions' if semantic == 'POSITION' else 'nonfinite_uv_corners' if semantic.startswith('TEXCOORD_') else None
                    if key is None or (key, index) in seen:
                        continue
                    index = integer(index)
                    seen.add((key, index)); accessor = document['accessors'][index]
                    if accessor['componentType'] != 5126:
                        continue  # Integer components cannot encode NaN/Inf.
                    components = {'SCALAR':1, 'VEC2':2, 'VEC3':3, 'VEC4':4}[accessor['type']]
                    accessor_count = integer(accessor['count'])
                    ranges = []
                    if 'bufferView' in accessor:
                        ranges.append((accessor['bufferView'], accessor.get('byteOffset', 0), accessor['count'], False))
                    if 'sparse' in accessor:
                        sparse = accessor['sparse']; values = sparse['values']
                        if integer(sparse['count']) > accessor_count:
                            raise ValueError('sparse count exceeds accessor count')
                        ranges.append((values['bufferView'], values.get('byteOffset', 0), sparse['count'], True))
                    for view_index, relative, count, sparse in ranges:
                        view = document['bufferViews'][integer(view_index)]
                        if 'EXT_meshopt_compression' in view.get('extensions', {}):
                            raise ValueError('compressed buffer view unsupported by numeric preflight')
                        if view.get('buffer', 0) != 0 or document['buffers'][0].get('uri'):
                            raise ValueError('external buffer unsupported by numeric preflight')
                        relative = integer(relative); count = integer(count)
                        view_offset = integer(view.get('byteOffset', 0)); view_length = integer(view['byteLength'])
                        start = view_offset+relative
                        stride = integer(components*4 if sparse else view.get('byteStride', components*4))
                        if view_offset+view_length > buffer_length or relative > view_length or stride < components*4 or stride % 4 or start % 4 or (count and relative+(count-1)*stride+components*4 > view_length):
                            raise ValueError('invalid numeric accessor bounds')
                        for i in range(count):
                            values = struct.unpack_from('<'+'f'*components, binary, start+i*stride)
                            metrics[key] += not all(math.isfinite(x) for x in values)
        return metrics
    except (KeyError, IndexError, struct.error, TypeError) as exc:
        raise ValueError('invalid GLB numeric accessor: '+str(exc)) from exc


def exact_topology_metrics(positions, triangles):
    """Geometric triangle incidence using exact positions, never UV vertex indices.

    Counts ignore degenerate triangles for edge incidence, include duplicate
    triangles in incidence, and measure edges with >2 incident triangles as
    nonmanifold. This does not prove orientability or absence of intersections.
    """
    clusters = {}; mapped = []
    for point in positions:
        key = tuple(point)
        mapped.append(clusters.setdefault(key, len(clusters)))
    edges = Counter(); faces = set(); duplicate = degenerate = count = 0
    for triangle in triangles:
        count += 1
        a, b, c = [mapped[i] for i in triangle]
        pa, pb, pc = [positions[i] for i in triangle]
        u = [pb[i]-pa[i] for i in range(3)]
        v = [pc[i]-pa[i] for i in range(3)]
        cross = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
        if len({a, b, c}) < 3 or not all(math.isfinite(x) for x in cross) or cross == (0, 0, 0):
            degenerate += 1; continue
        face = tuple(sorted((a, b, c)))
        duplicate += face in faces; faces.add(face)
        for x, y in ((a, b), (b, c), (c, a)):
            edges[(min(x, y), max(x, y))] += 1
    return {'vertices': len(positions), 'triangles': count,
            'position_clusters': len(clusters),
            'duplicate_position_vertices': len(positions)-len(clusters),
            'nonfinite_positions': sum(not all(math.isfinite(x) for x in point) for point in positions),
            'nonfinite_uv_corners': 0,
            'boundary_edges': sum(n == 1 for n in edges.values()),
            'nonmanifold_edges': sum(n > 2 for n in edges.values()),
            'degenerate_faces': degenerate, 'duplicate_faces': duplicate}


def require_topology_nonregression(before, after):
    for phase, metrics in (('before', before), ('after', after)):
        invalid = [f'{key}={metrics.get(key, 0)}' for key in ('nonfinite_positions', 'nonfinite_uv_corners')
                   if metrics.get(key, 0)]
        if invalid:
            raise ValueError('nonfinite geometry/UV ' + phase + '; no output published: ' + '; '.join(invalid))
    increased = [f'{key}: {before[key]} -> {after[key]}'
                 for key in ('boundary_edges', 'nonmanifold_edges', 'degenerate_faces', 'duplicate_faces')
                 if after[key] > before[key]]
    if increased:
        raise ValueError('topology regression; no output published: ' + '; '.join(increased))


def mesh_topology(obj):
    mesh = obj.data; mesh.calc_loop_triangles()
    # Object-local exact clustering matches the zero-distance BMesh preparation.
    result = exact_topology_metrics([tuple(v.co) for v in mesh.vertices],
                                   (tuple(t.vertices) for t in mesh.loop_triangles))
    result['nonfinite_uv_corners'] = sum(not all(math.isfinite(x) for x in loop.uv)
                                          for layer in mesh.uv_layers for loop in layer.data)
    result['faces'] = len(mesh.polygons)
    result['custom_normals'] = mesh.has_custom_normals
    result['bbox_local'] = None if result['nonfinite_positions'] else [[min((v.co[i] for v in mesh.vertices), default=0) for i in range(3)],
                            [max((v.co[i] for v in mesh.vertices), default=0) for i in range(3)]]
    return result


def corner_signatures(mesh):
    """All UV layers and exact positions, cyclic ordering and material retained."""
    signatures = Counter()
    for face in mesh.polygons:
        corners = [tuple(mesh.vertices[mesh.loops[i].vertex_index].co) +
                   tuple(x for layer in mesh.uv_layers for x in layer.data[i].uv)
                   for i in face.loop_indices]
        # Keep winding while allowing the first loop to change after BMesh.
        start = min(range(len(corners)), key=lambda i: corners[i:]+corners[:i])
        signature = (face.material_index, corners[start:]+corners[:start])
        signatures[hashlib.sha256(repr(signature).encode()).digest()] += 1
    return signatures


def uv_triangle_metrics(triangles, resolution):
    areas = []; nonfinite = 0; outside = 0
    for triangle in triangles:
        if not all(math.isfinite(v) for point in triangle for v in point):
            nonfinite += 1; areas.append(0.0); continue
        outside += int(any(v < -1e-6 or v > 1 + 1e-6 for point in triangle for v in point))
        a, b, c = triangle
        areas.append(abs((b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])) / 2)
    return {'triangles': len(areas), 'summed_uv_area': sum(areas),
            'degenerate_uv_triangles': sum(a <= 1e-14 for a in areas),
            'nonfinite_uv_triangles': nonfinite, 'outside_unit_atlas_triangles': outside,
            'sub_half_texel_triangles': sum(a < .5 / resolution**2 for a in areas),
            'resolution': resolution,
            'limitations': ['summed area does not prove nonoverlap',
                            'UV area does not measure bake ray hits or aesthetic quality']}


def require_uv_quality(metrics):
    if not metrics['triangles'] or metrics['nonfinite_uv_triangles'] or metrics['degenerate_uv_triangles']:
        raise ValueError('empty, nonfinite or degenerate UV triangles; no atlas published')
    if metrics['outside_unit_atlas_triangles']:
        raise ValueError('UV triangles outside the unit atlas; no atlas published')
    if metrics['summed_uv_area'] < .05:
        raise ValueError('sparse UV atlas: summed triangle area below 5%; no atlas published')
    if metrics['summed_uv_area'] > 1.000001:
        raise ValueError('summed UV area exceeds unit atlas; overlap or out-of-bounds UVs')


def uv_quality(obj, resolution):
    if not obj.data.uv_layers.active:
        return uv_triangle_metrics([], resolution)
    obj.data.calc_loop_triangles(); data = obj.data.uv_layers.active.data
    return uv_triangle_metrics([[tuple(data[i].uv) for i in tri.loops]
                                for tri in obj.data.loop_triangles], resolution)


def main(cfg):
    output = Path(cfg['output']); report_path = Path(cfg['report'])
    if output.exists() or report_path.exists() or output.resolve() == Path(cfg['model']).resolve():
        raise ValueError('refusing to overwrite input or existing output/report')
    source_numeric = {}
    if cfg['operation'] == 'optimize':
        try:
            source_numeric = glb_nonfinite_metrics(cfg['model'])
            invalid = [f'{key}={source_numeric.get(key, 0)}' for key in ('nonfinite_positions', 'nonfinite_uv_corners') if source_numeric.get(key, 0)]
            if invalid:
                raise ValueError('nonfinite encoded source; no output published: '+'; '.join(invalid))
        except (ValueError, RuntimeError) as exc:
            report_path.write_text(json.dumps({'operation': 'optimize', 'status': 'rejected',
                'source': {'numeric_preflight': source_numeric}, 'error': str(exc),
                'visual_approval': 'pending'}, indent=2), encoding='utf-8')
            raise
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.gltf(filepath=cfg['model'])
    objects = meshes()
    if not objects:
        raise ValueError('no visible mesh objects')
    for obj in bpy.context.scene.objects:
        if obj.type == 'ARMATURE' or obj.animation_data and (obj.animation_data.action or obj.animation_data.nla_tracks):
            raise ValueError('animated/skinned input unsupported; provide static mesh')
    for obj in objects:
        if any(m.type == 'ARMATURE' for m in obj.modifiers) or obj.data.shape_keys:
            raise ValueError('skinned/deforming input unsupported; provide static mesh')
    source = stats(objects)
    if cfg['operation'] == 'optimize':
        source['numeric_preflight'] = source_numeric
    operation = cfg['operation']; params = cfg['params']; details = {}
    if operation == 'segment':
        groups = {o.name: component_groups(o.data) for o in objects}
        counts = {name: len(parts) for name, parts in groups.items()}
        if sum(counts.values()) > params['max_parts']:
            raise ValueError(f"geometric component count {sum(counts.values())} exceeds max_parts; no output written")
        parts = []
        for obj in objects:
            for index, group in enumerate(groups[obj.name]):
                part = obj.copy(); part.data = obj.data.copy(); part.name = f'{obj.name}_part_{index:03d}'
                bpy.context.scene.collection.objects.link(part)
                bm = bmesh.new(); bm.from_mesh(part.data); bm.verts.ensure_lookup_table()
                keep = set(group)
                bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.index not in keep], context='VERTS')
                bm.to_mesh(part.data); bm.free(); parts.append(part)
            obj.hide_render = True; obj.hide_set(True)
        objects = parts
        details = {'method': 'edge connectivity plus exact coincident-position adjacency; no vertex welding, no semantic classification',
                   'source_component_counts': counts, 'parts': [o.name for o in objects],
                   'warning': 'Exact coincident geometry can join touching parts; UVs and disconnected source vertices retained. No geometry removed.'}
    elif operation == 'optimize':
        weld = params.get('weld_seams', True)
        if not isinstance(weld, bool):
            raise ValueError('weld_seams must be a boolean')
        per_object = []
        details = {'ratio_requested': params['ratio'], 'weld_seams': weld,
                   'weld_tolerance_object_units': 0.0 if weld else None,
                   'topology_method': 'exact object-local position clusters; boundary incidence=1; nonmanifold incidence>2; degenerate faces excluded from incidence',
                   'per_object': per_object, 'uv_changed': True,
                   'warning': 'Exact welding may merge intentionally touching surfaces and removes duplicate/degenerate source faces. '
                              'Surviving face position/UV corner data is checked before decimation; normals may change. '
                              'Decimation may distort UVs and texture appearance. Residual defects remain explicit; '
                              'counts do not prove watertightness, intersections, silhouette, or visual quality.'}
        try:
            # A linked instance must not mutate another object's original mesh.
            for obj in objects:
                if obj.data.users > 1:
                    obj.data = obj.data.copy()
            for obj in objects:
                activate(obj)
                original = mesh_topology(obj)
                record = {'object': obj.name, 'original': original}
                per_object.append(record)
                # Reject invalid numeric data before hashing corners or invoking BMesh.
                require_topology_nonregression(original, original)
                if weld:
                    before_corners = corner_signatures(obj.data)
                    bm = bmesh.new()
                    try:
                        bm.from_mesh(obj.data)
                        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.0)
                        bm.to_mesh(obj.data)
                    finally:
                        bm.free()
                    obj.data.update()
                    after_corners = corner_signatures(obj.data)
                    record['weld_corner_data_changed_faces'] = sum((after_corners-before_corners).values())
                    record['weld_removed_face_corner_signatures'] = sum((before_corners-after_corners).values())
                    del before_corners, after_corners
                prepared = mesh_topology(obj)
                record['prepared'] = prepared
                record['weld_vertices_removed'] = original['vertices']-prepared['vertices']
                record['weld_faces_removed'] = original['faces']-prepared['faces']
                record['weld_bbox_max_abs_deviation'] = max(abs(original['bbox_local'][j][i]-prepared['bbox_local'][j][i])
                                                           for j in range(2) for i in range(3))
                require_topology_nonregression(prepared, prepared)
                if weld:
                    if record['weld_corner_data_changed_faces'] or record['weld_bbox_max_abs_deviation']:
                        raise ValueError('exact weld changed surviving position/UV corners or bounds; no output published')
                    if all(original[key] == 0 for key in ('boundary_edges', 'nonmanifold_edges', 'degenerate_faces', 'duplicate_faces')):
                        require_topology_nonregression(original, prepared)
                modifier = obj.modifiers.new('OpenFiguraDecimate', 'DECIMATE'); modifier.ratio = params['ratio']
                bpy.ops.object.modifier_apply(modifier=modifier.name)
                record['result'] = mesh_topology(obj)
                # Compare to actual prepared geometry, also when welding is disabled.
                require_topology_nonregression(prepared, record['result'])
        except (ValueError, RuntimeError) as exc:
            report_path.write_text(json.dumps({'operation': operation, 'status': 'rejected',
                'source': source, 'candidate': stats(objects), 'details': details,
                'error': str(exc), 'visual_approval': 'pending'}, indent=2), encoding='utf-8')
            raise
    elif operation == 'retopo':
        deviations = []; modes = []
        for obj in objects:
            activate(obj)
            bm = bmesh.new(); bm.from_mesh(obj.data)
            bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.000001)
            bm.to_mesh(obj.data); bm.free()
            obj.data.calc_loop_triangles()
            tree = BVHTree.FromPolygons([v.co.copy() for v in obj.data.vertices], [tuple(t.vertices) for t in obj.data.loop_triangles], all_triangles=True)
            # QuadriFlow needs a closed manifold: generated meshes are not.
            # Voxel remesh first (guaranteed watertight), then quad pass.
            size = params.get('voxel_size') or max(0.001, max(bounding_box(obj)) / 200.0)
            modifier = obj.modifiers.new('OpenFiguraVoxel', 'REMESH'); modifier.mode = 'VOXEL'; modifier.voxel_size = size
            bpy.ops.object.modifier_apply(modifier=modifier.name)
            quad = bpy.ops.object.quadriflow_remesh(target_faces=params['target_faces'], use_mesh_symmetry=False, use_preserve_sharp=False, use_preserve_boundary=True)
            modes.append({'object': obj.name, 'voxel_size': size,
                          'quadriflow': 'finished' if 'FINISHED' in quad else 'cancelled, kept watertight triangulated output'})
            for vertex in obj.data.vertices:
                nearest = tree.find_nearest(vertex.co)
                if nearest and nearest[0] is not None:
                    deviations.append(nearest[3])
        details = {'target_faces_per_object': params['target_faces'],
                   'pipeline': 'weld 1e-6 -> voxel remesh (watertight shell) -> QuadriFlow when it accepts the result',
                   'per_object': modes, 'uv_changed': True, 'requires_rebake': True,
                   'deviation': {'method': 'new vertices to nearest source triangle, object-local units; one-way sample, not Hausdorff',
                                 'max': max(deviations, default=0), 'mean': sum(deviations)/len(deviations) if deviations else 0},
                   'warning': 'Topology and UVs are replaced. Voxel remesh seals concavities and adds shell thickness; texture appearance is not preserved; baking unsupported.'}
    elif operation == 'collision':
        hulls = []
        for obj in objects:
            bm = bmesh.new(); bm.from_mesh(obj.data)
            hull = bmesh.ops.convex_hull(bm, input=list(bm.verts), use_existing_faces=False)
            discard = list(set(hull.get('geom_interior', []) + hull.get('geom_unused', [])))
            if discard:
                bmesh.ops.delete(bm, geom=discard, context='VERTS')
            mesh = bpy.data.meshes.new(obj.name + '_collision'); bm.to_mesh(mesh); bm.free()
            collision = bpy.data.objects.new(obj.name + '_collision', mesh)
            bpy.context.scene.collection.objects.link(collision); collision.matrix_world = obj.matrix_world.copy()
            hulls.append(collision)
        objects = hulls
        details = {'method': 'one convex hull per source mesh', 'render_geometry_included': False,
                   'warning': 'Collision-only output; convex hulls fill concavities and contain no source materials.'}
    elif operation == 'uv':
        per_object = []; changed = False
        for obj in objects:
            activate(obj)
            before = uv_quality(obj, params['resolution']); mode = params['mode']
            if mode == 'auto':
                try:
                    require_uv_quality(before); mode = 'preserve'
                except ValueError:
                    mode = 'unwrap'
            if mode == 'preserve':
                require_uv_quality(before)
            else:
                changed = True
                if mode == 'unwrap':
                    for layer in list(obj.data.uv_layers):
                        obj.data.uv_layers.remove(layer)
                    obj.data.uv_layers.new(name='OpenFiguraUV')
                elif not obj.data.uv_layers.active:
                    raise ValueError('repack needs an existing UV layer')
                bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
                if mode == 'unwrap':
                    bpy.ops.uv.smart_project(island_margin=0)
                bpy.ops.uv.select_all(action='SELECT')
                bpy.ops.uv.pack_islands(margin_method='FRACTION',
                                       margin=params['margin_pixels']/params['resolution'],
                                       rotate=True, scale=True)
                bpy.ops.object.mode_set(mode='OBJECT')
            after = uv_quality(obj, params['resolution'])
            per_object.append({'object': obj.name, 'method': mode, 'before': before, 'after': after})
            try:
                require_uv_quality(after)
            except ValueError as exc:
                report_path.write_text(json.dumps({'operation': operation, 'status': 'rejected',
                    'source': source, 'details': {'per_object': per_object},
                    'error': str(exc), 'visual_approval': 'pending'}, indent=2), encoding='utf-8')
                raise
        details = {'uv_changed': changed, 'requires_rebake': changed, 'mode_requested': params['mode'],
                   'margin_pixels': params['margin_pixels'], 'resolution': params['resolution'],
                   'per_object': per_object,
                   'warning': 'Auto preserves existing UVs that clear technical area/degeneracy checks. '
                              'Unwrap/repack changes texture mapping and requires rebaking. '
                              'This does not prove nonoverlap, ray coverage or visual quality.'}
    else:
        raise ValueError('unsupported operation')
    result = stats(objects)
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(output), export_format='GLB', use_selection=True,
                              export_yup=True, export_animations=False, export_skins=False)
    report = {'operation': operation, 'source': source, 'result': result, 'details': details,
              'visual_approval': 'pending', 'axis': 'glTF Y-up', 'output': str(output)}
    report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('OPENFIGURA_MESH_DONE')


if __name__ == '__main__':
    main(json.loads(Path(sys.argv[-1]).read_text(encoding='utf-8')))
