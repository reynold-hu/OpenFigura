"""Original Blender CPU Cycles selected-to-active baking worker."""
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

import bpy
from mathutils import Vector


def glb_json(path):
    data = Path(path).read_bytes()
    if len(data) < 20 or data[:4] != b'glTF': raise ValueError('invalid GLB')
    size, kind = struct.unpack_from('<II', data, 12)
    if kind != 0x4e4f534a: raise ValueError('missing GLB JSON')
    return json.loads(data[20:20+size])


def import_static(path):
    doc = glb_json(path)
    if doc.get('skins') or doc.get('animations') or any('targets' in p for m in doc.get('meshes', []) for p in m.get('primitives', [])):
        raise ValueError('bake accepts static GLBs only; bake before autorig')
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    objects = set(bpy.context.scene.objects)-before
    meshes = [o for o in objects if o.type == 'MESH']
    if not meshes: raise ValueError('input has no mesh')
    return objects, meshes


def triangles(meshes):
    return sum(sum(max(0, len(p.vertices)-2) for p in o.data.polygons) for o in meshes)


def bounds(meshes):
    points = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    return [[min(p[i] for p in points) for i in range(3)], [max(p[i] for p in points) for i in range(3)]]


def uv_digest(obj):
    return hashlib.sha256(b''.join(struct.pack('<ff', *loop.uv) for loop in obj.data.uv_layers.active.data)).hexdigest()


def image_metrics(img):
    values = list(img.pixels[:])
    total = len(values)//4
    covered = [i for i in range(total) if values[4*i+3] > .5]
    channels = []
    for c in range(3):
        v = [values[4*i+c] for i in covered]
        mean = sum(v)/len(v) if v else 0
        channels.append({'min': min(v) if v else 0, 'max': max(v) if v else 0,
                         'variance': sum((x-mean)**2 for x in v)/len(v) if v else 0})
    return {'covered_pixels': len(covered), 'coverage_fraction': len(covered)/total,
            'coverage_method': 'alpha > 0.5; includes bake margin, not a ray-hit coverage measurement',
            'channels': channels, 'nonconstant': any(c['variance'] > 1e-8 for c in channels)}


def main():
    cfg = json.loads(Path(sys.argv[-1]).read_text())
    params = cfg['params']
    artifacts = [cfg['output'], cfg['report'], cfg['blend'], *cfg['textures'].values()]
    if any(Path(p).exists() for p in artifacts): raise ValueError('refusing existing artifacts')
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    high_objects, high = import_static(cfg['high'])
    low_objects, low = import_static(cfg['low'])
    if len(low) != 1:
        raise ValueError('initial bake requires one target mesh; multiple mesh UV atlases need explicit packing')
    target = low[0]
    if not target.data.uv_layers.active: raise ValueError('target must have an existing UV map')
    initial_uv = uv_digest(target)
    hb, lb = bounds(high), bounds(low)
    if any(min(hb[1][i], lb[1][i]) <= max(hb[0][i], lb[0][i]) for i in range(3)):
        raise ValueError('source and target bounds are disjoint or degenerate')
    extent = [lb[1][i]-lb[0][i] for i in range(3)]
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'; scene.cycles.device = 'CPU'; scene.cycles.samples = params['samples']
    bake = scene.render.bake
    bake.use_selected_to_active = True
    bake.cage_extrusion = params['cage_extrusion']; bake.max_ray_distance = params['ray_distance']
    bake.normal_space = 'TANGENT'; bake.margin = 8
    # Separate target materials from any source materials and cover empty slots.
    if not target.data.materials: target.data.materials.append(bpy.data.materials.new('BakedMaterial'))
    materials = []
    for i, mat in enumerate(target.data.materials):
        mat = mat.copy() if mat else bpy.data.materials.new('BakedMaterial')
        target.data.materials[i] = mat; mat.use_nodes = True; materials.append(mat)
    images, metrics = {}, {}
    for map_name in params['maps']:
        img = bpy.data.images.new('Baked-'+map_name, width=params['resolution'], height=params['resolution'], alpha=True)
        img.colorspace_settings.name = 'Non-Color'; img.generated_color = (0, 0, 0, 0)
        for mat in materials:
            nodes = mat.node_tree.nodes
            for node in nodes: node.select = False
            node = nodes.new('ShaderNodeTexImage'); node.image = img; node.select = True; nodes.active = node
        bpy.ops.object.select_all(action='DESELECT')
        for obj in high: obj.select_set(True)
        target.select_set(True); bpy.context.view_layer.objects.active = target
        bpy.ops.object.bake(type='NORMAL' if map_name == 'normal' else 'AO')
        metrics[map_name] = image_metrics(img)
        if not metrics[map_name]['covered_pixels']: raise ValueError('bake has no covered pixels')
        img.filepath_raw = cfg['textures'][map_name]; img.file_format = 'PNG'; img.save()
        images[map_name] = img
    for mat in materials:
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        shader = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
        if 'normal' in images:
            tex = nodes.new('ShaderNodeTexImage'); tex.image = images['normal']
            normal = nodes.new('ShaderNodeNormalMap')
            links.new(tex.outputs['Color'], normal.inputs['Color']); links.new(normal.outputs['Normal'], shader.inputs['Normal'])
        if 'ao' in images:
            group = bpy.data.node_groups.get('glTF Material Output')
            if group is None:
                group = bpy.data.node_groups.new('glTF Material Output', 'ShaderNodeTree')
                group.interface.new_socket(name='Occlusion', in_out='INPUT', socket_type='NodeSocketFloat')
            output = nodes.new('ShaderNodeGroup'); output.node_tree = group
            tex = nodes.new('ShaderNodeTexImage'); tex.image = images['ao']
            links.new(tex.outputs['Color'], output.inputs['Occlusion'])
    bpy.ops.object.select_all(action='DESELECT')
    for obj in low_objects: obj.select_set(True)
    bpy.context.view_layer.objects.active = target
    bpy.ops.export_scene.gltf(filepath=cfg['output'], export_format='GLB', use_selection=True, export_animations=False)
    doc = glb_json(cfg['output'])
    for name in params['maps']:
        key = 'normalTexture' if name == 'normal' else 'occlusionTexture'
        if not all(key in mat for mat in doc.get('materials', [])) or not doc.get('materials'):
            raise ValueError(f'GLB did not attach {key} to every material')
    if not doc.get('images') or not all('bufferView' in img for img in doc['images']):
        raise ValueError('GLB textures are not embedded')
    for img in images.values(): img.pack()
    for obj in high_objects: obj.hide_render = True; obj.hide_set(True)
    bpy.ops.wm.save_as_mainfile(filepath=cfg['blend'])
    if uv_digest(target) != initial_uv: raise ValueError('target UV changed')
    result_tris = sum(doc['accessors'][p['indices']]['count']//3 for m in doc['meshes'] for p in m['primitives'])
    report = {'source_triangles': triangles(high), 'target_triangles': triangles(low), 'result_triangles': result_tris,
              'uv_preserved': True, 'uv_sha256': initial_uv, 'source_bounds': hb, 'target_bounds': lb,
              'target_extent': extent, 'bounds_overlap': True, 'settings': params, 'textures': metrics,
              'device': 'CPU', 'engine': 'CYCLES', 'selected_to_active': True, 'visual_approval': 'pending',
              'limitations': ['Bounds overlap is a coarse alignment check; inspect ray misses and seams visually.',
                              'Single target mesh only; existing UV islands must not overlap.',
                              'Nonconstant texture statistics do not establish aesthetic quality.']}
    Path(cfg['report']).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('BAKE_DONE', flush=True)


if __name__ == '__main__': main()
