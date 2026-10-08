"""Blender-only worker. Original implementation; no third-party copied scripts."""
import json
import sys
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


def main(cfg):
    output = Path(cfg['output']); report_path = Path(cfg['report'])
    if output.exists() or report_path.exists() or output.resolve() == Path(cfg['model']).resolve():
        raise ValueError('refusing to overwrite input or existing output/report')
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
        for obj in objects:
            activate(obj)
            modifier = obj.modifiers.new('OpenFiguraDecimate', 'DECIMATE'); modifier.ratio = params['ratio']
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        details = {'ratio_requested': params['ratio'], 'uv_changed': True,
                   'warning': 'Material slots retained; decimation may distort UVs and texture appearance. Visual review required.'}
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
        for obj in objects:
            activate(obj)
            for layer in list(obj.data.uv_layers):
                obj.data.uv_layers.remove(layer)
            obj.data.uv_layers.new(name='OpenFiguraUV')
            bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.uv.smart_project(island_margin=0.02); bpy.ops.object.mode_set(mode='OBJECT')
        details = {'uv_changed': True, 'requires_rebake': True,
                   'warning': 'All source UV layers replaced by smart projection. Material slots retained; old textures will map differently.'}
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
