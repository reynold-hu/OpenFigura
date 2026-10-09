"""Blender-only fixed pose evidence worker; numeric summaries are stdlib-testable."""
import hashlib
import json
import math
from pathlib import Path
import struct
import sys


def displacement_report(rest, posed, tracked, labels, sample_limit=20):
    if len(rest) != len(posed) or len(labels) != len(rest):
        raise ValueError('topology changed: vertex count differs')
    values = [(math.dist(rest[i], posed[i]), i) for i in tracked]
    if any(not math.isfinite(value) for value, _ in values):
        raise ValueError('nonfinite displacement')
    ordered = sorted(value for value, _ in values)
    def quantile(fraction):
        if not ordered: return 0.0
        index = (len(ordered)-1)*fraction; low = int(index); high = math.ceil(index)
        return ordered[low] + (ordered[high]-ordered[low])*(index-low)
    return {'tracked_vertices': len(tracked), 'peak_world_units': max(ordered, default=0.0),
            'quantiles_world_units': {str(q): quantile(q) for q in (.5, .9, .95, .99)},
            'over_002_world_units': sum(value > .002 for value, _ in values),
            'worst_samples': [{'vertex_index': i, 'original_dominant_group': labels[i],
                               'rest_world': list(rest[i]), 'posed_world': list(posed[i]),
                               'displacement_world_units': value}
                              for value, i in sorted(values, reverse=True)[:sample_limit]]}


def frame_bounds(points):
    if not points: raise ValueError('no renderable vertices')
    lower = [min(p[i] for p in points) for i in range(3)]
    upper = [max(p[i] for p in points) for i in range(3)]
    center = [(low+high)/2 for low, high in zip(lower, upper)]
    scale = max(upper[0]-lower[0], upper[2]-lower[2])*1.15
    if not all(math.isfinite(v) for v in [*center, scale]) or scale <= 0:
        raise ValueError('degenerate render bounds')
    return center, scale


def main():
    import bpy
    from mathutils import Matrix, Vector

    cfg = json.loads(Path(sys.argv[-1]).read_text(encoding='utf-8'))
    out = Path(cfg['output_dir']); params = cfg['params']; report_path = out/'skin-probe-report.json'
    report = {'schema_version': 1, 'status': 'failed', 'probes': [],
              'skin_quality_accepted': False, 'collision_checked': False, 'collision_accepted': False,
              'visual_approval': 'pending', 'settings': params, 'vertex_index_domain': 'imported_blender_mesh_local', 'track_mask_method': 'frozen_union_of_original_positive_weight_memberships', 'original_label_method': 'largest_original_positive_weight_group',
              'limitations': ['Displacement greater than 0.002 GLB world units is a diagnostic, not a collision gate.',
                             'Frozen positive-weight group membership and original dominant labels are not semantic segmentation.',
                             'Vertex indices are imported Blender mesh local IDs, not raw GLB primitive accessor IDs.',
                             'No weight correction, collision test, or accepted animation is produced.',
                             'Closeups use a fixed +Y front view and can hide back-facing defects; human inspection remains pending.',
                             'Diagnostic blend keyframes contain isolated local-axis probes, not a delivered animation.']}
    try:
        if report_path.exists(): raise ValueError('existing report refused')
        source = Path(cfg['model']); source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
        report['source_sha256'] = source_sha
        bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
        bpy.ops.import_scene.gltf(filepath=str(source))
        scene = bpy.context.scene
        meshes = [o for o in scene.objects if o.type == 'MESH' and not o.hide_render and o.visible_get()]
        skinned = [o for o in meshes if any(m.type == 'ARMATURE' and m.object for m in o.modifiers)]
        arms = {m.object for o in skinned for m in o.modifiers if m.type == 'ARMATURE' and m.object}
        if len(arms) != 1 or not skinned: raise ValueError('exactly one armature with skinned meshes required')
        arm = next(iter(arms))
        for obj in skinned:
            if any(m.type != 'ARMATURE' for m in obj.modifiers) or sum(m.type == 'ARMATURE' for m in obj.modifiers) != 1:
                raise ValueError('only a single armature modifier per mesh supported; topology-changing modifiers refused')
            if obj.data.shape_keys: raise ValueError('shape keys unsupported for fixed rest probes')
        if any(o.animation_data and o.animation_data.action for o in scene.objects):
            raise ValueError('source animation unsupported')
        original_basis = {bone.name: bone.matrix_basis.copy() for bone in arm.pose.bones}
        def restore():
            for bone in arm.pose.bones: bone.matrix_basis = original_basis[bone.name].copy()
            bpy.context.view_layer.update()
        def positions(obj):
            depsgraph = bpy.context.evaluated_depsgraph_get(); evaluated = obj.evaluated_get(depsgraph)
            mesh = evaluated.to_mesh()
            try:
                if len(mesh.vertices) != len(obj.data.vertices): raise ValueError('evaluated vertex topology changed')
                return [tuple(evaluated.matrix_world @ vertex.co) for vertex in mesh.vertices]
            finally: evaluated.to_mesh_clear()
        restore()
        baseline, labels, memberships = {}, {}, {}
        for obj in skinned:
            baseline[obj.name] = positions(obj)
            names = {g.index: g.name for g in obj.vertex_groups}
            labels[obj.name] = []
            memberships[obj.name] = []
            for vertex in obj.data.vertices:
                weighted = [(g.weight, names[g.group]) for g in vertex.groups if g.weight > 0]
                labels[obj.name].append(max(weighted, default=(0, None))[1])
                memberships[obj.name].append({name for _, name in weighted})
        masks = []
        for probe in params['probes']:
            if probe['bone'] not in original_basis: raise ValueError('unknown exact probe bone: '+probe['bone'])
            for group in probe['track_groups']:
                if not any(group in groups for rows in memberships.values() for groups in rows):
                    raise ValueError('absent or empty track group: '+group)
            selected = set(probe['track_groups'])
            masks.append({obj.name: [i for i, groups in enumerate(memberships[obj.name]) if groups & selected] for obj in skinned})
        report['baseline'] = [{'mesh': obj.name, 'vertices': len(baseline[obj.name]),
                               'world_positions_sha256': hashlib.sha256(b''.join(struct.pack('<ddd', *p) for p in baseline[obj.name])).hexdigest(),
                               'original_labels_sha256': hashlib.sha256(json.dumps(labels[obj.name]).encode()).hexdigest()}
                              for obj in skinned]
        all_points = [Vector(p) for obj in meshes for p in positions(obj)]
        if not all_points: raise ValueError('no renderable vertices')
        lower = Vector(tuple(min(p[i] for p in all_points) for i in range(3)))
        upper = Vector(tuple(max(p[i] for p in all_points) for i in range(3)))
        center = (lower+upper)/2; extent = max(upper-lower)
        if not math.isfinite(extent) or extent <= 0: raise ValueError('degenerate model bounds')
        scene.unit_settings.system = 'METRIC'; scene.unit_settings.scale_length = 1.0
        scene.render.engine = 'CYCLES'; scene.cycles.device = 'CPU'; scene.cycles.samples = params['samples']
        scene.render.resolution_x = scene.render.resolution_y = params['resolution']; scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = 'PNG'
        scene.world.color = (.2, .2, .2)
        camera_data = bpy.data.cameras.new('SkinProbeCamera'); camera = bpy.data.objects.new('SkinProbeCamera', camera_data)
        scene.collection.objects.link(camera); scene.camera = camera; camera_data.type = 'ORTHO'
        camera.rotation_euler = Vector((0,-1,0)).to_track_quat('-Z', 'Y').to_euler()
        for name, offset, energy in [('Key', (2,3,3), 900), ('Fill', (-2,2,1), 500), ('Rim', (0,-2,3), 700)]:
            data = bpy.data.lights.new('SkinProbe'+name, 'AREA'); data.energy = energy*extent*extent; data.shape = 'DISK'; data.size = extent*2
            light = bpy.data.objects.new('SkinProbe'+name, data); scene.collection.objects.link(light)
            light.location = center + Vector(offset)*extent
            light.rotation_euler = (center-light.location).to_track_quat('-Z','Y').to_euler()
        def render(name, focus, scale):
            camera.location = Vector((focus.x, upper.y + extent*3, focus.z))
            camera_data.ortho_scale = scale
            scene.render.filepath = str(out/name); bpy.ops.render.render(write_still=True)
        render('rest-full.png', center, max(upper.x-lower.x, upper.z-lower.z)*1.15)
        states = []
        for index, (probe, mask) in enumerate(zip(params['probes'], masks), 1):
            restore()
            bone = arm.pose.bones[probe['bone']]
            bone.matrix_basis = original_basis[bone.name] @ Matrix.Rotation(math.radians(probe['degrees']), 4, probe['axis'])
            bpy.context.view_layer.update()
            record = {**probe, 'meshes': [], 'displacement_threshold_world_units': .002,
                      'full_frame': f'probe-{index:03d}-full.png', 'closeup_frame': f'probe-{index:03d}-closeup.png'}
            largest = None
            for obj in skinned:
                posed = positions(obj)
                tracked = displacement_report(baseline[obj.name], posed, mask[obj.name], labels[obj.name])
                tracked['mesh'] = obj.name
                tracked['frozen_track_mask_sha256'] = hashlib.sha256(b''.join(struct.pack('<I', i) for i in mask[obj.name])).hexdigest()
                record['meshes'].append(tracked)
                if tracked['worst_samples']:
                    worst = tracked['worst_samples'][0]
                    if largest is None or worst['displacement_world_units'] > largest['displacement_world_units']:
                        largest = {**worst, 'mesh': obj.name}
            focus = Vector(largest['posed_world']) if largest and largest['displacement_world_units'] > 0 else arm.matrix_world @ bone.head
            record['closeup_center_world'] = list(focus); record['closeup_basis'] = 'largest_moved_tracked_vertex' if largest and largest['displacement_world_units'] > 0 else 'probe_bone_head'
            record['largest_moved_tracked_vertex'] = largest
            full_center, full_scale = frame_bounds([p for obj in meshes for p in positions(obj)])
            record['full_frame_center_world'] = full_center; record['full_frame_ortho_scale'] = full_scale
            render(record['full_frame'], Vector(full_center), full_scale)
            render(record['closeup_frame'], focus, extent*params['crop_extent_ratio'])
            states.append({b.name: b.matrix_basis.copy() for b in arm.pose.bones})
            report['probes'].append(record)
        restore()
        # Key every bone at every isolated frame, including a native rest frame.
        for frame, state in [(1, original_basis)] + [(i+2, state) for i, state in enumerate(states)]:
            for bone in arm.pose.bones:
                bone.rotation_mode = 'QUATERNION'; bone.matrix_basis = state[bone.name].copy()
                for channel in ('location', 'rotation_quaternion', 'scale'): bone.keyframe_insert(data_path=channel, frame=frame)
        action = arm.animation_data.action
        curves = getattr(action, 'fcurves', None)
        if curves is None:
            curves = [curve for layer in action.layers for strip in layer.strips
                      for bag in strip.channelbags for curve in bag.fcurves]
        for curve in curves:
            for key in curve.keyframe_points: key.interpolation = 'CONSTANT'
        scene.frame_start = 1; scene.frame_end = len(states)+1; scene.frame_set(1); restore()
        camera.location = Vector((center.x, upper.y+extent*3, center.z)); camera_data.ortho_scale = max(upper.x-lower.x, upper.z-lower.z)*1.15
        for image in bpy.data.images:
            if image.has_data and image.source == 'FILE': image.pack()
        bpy.ops.wm.save_as_mainfile(filepath=str(out/'skin-probe.blend'))
        if hashlib.sha256(source.read_bytes()).hexdigest() != source_sha: raise ValueError('source changed during probe')
        report['status'] = 'complete'; report['device'] = 'CPU'; report['engine'] = 'CYCLES'; report['source_unchanged'] = True
    except BaseException as exc:
        report['status'] = 'failed'; report['error'] = f'{type(exc).__name__}: {exc}'
        with report_path.open('x', encoding='utf-8') as handle: json.dump(report, handle, indent=2, allow_nan=False)
        raise
    with report_path.open('x', encoding='utf-8') as handle: json.dump(report, handle, indent=2, allow_nan=False)
    print('SKIN_PROBE_COMPLETE', flush=True)


if __name__ == '__main__': main()
