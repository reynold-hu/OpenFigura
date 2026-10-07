"""Executed only inside Blender. Calibrated basic-human rig, explicit skin method."""
import bpy
import addon_utils
import json
import sys
import time
from pathlib import Path
from mathutils import Vector

cfg = json.loads(Path(sys.argv[-1]).read_text(encoding='utf-8'))
calibration = json.loads(Path(cfg['calibration']).read_text(encoding='utf-8'))
started = time.monotonic()
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
bpy.ops.import_scene.gltf(filepath=cfg['model'])
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH' and not o.hide_render]
if not meshes:
    raise ValueError('no renderable mesh')
for obj in meshes:
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    obj.select_set(False)
addon_utils.enable('rigify', default_set=True)
bpy.ops.object.armature_basic_human_metarig_add()
meta = bpy.context.object
meta.name = 'CalibratedMetarig'
bpy.ops.object.mode_set(mode='EDIT')
required = set(meta.data.edit_bones.keys())
if set(calibration['bones']) != required:
    raise ValueError(f'calibration must match basic-human template; missing={sorted(required-set(calibration["bones"]))}, extra={sorted(set(calibration["bones"])-required)}')
for name, coordinates in calibration['bones'].items():
    bone = meta.data.edit_bones[name]
    bone.head = Vector(coordinates['head'])
    bone.tail = Vector(coordinates['tail'])
bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.pose.rigify_generate()
rig = bpy.context.object
rig.name = 'CalibratedRig'
for obj in meshes:
    obj.select_set(True)
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
method = cfg['skin_method']
bpy.ops.object.parent_set(type='ARMATURE_AUTO' if method == 'automatic' else 'ARMATURE_NAME')
if method == 'capsule':
    import numpy as np
    bones = [b for b in rig.data.bones if b.use_deform]
    for obj in meshes:
        xyz = np.array([tuple(obj.matrix_world @ v.co) for v in obj.data.vertices])
        extent = max(float(np.ptp(xyz,axis=0).max()),1e-6)
        distances = []
        for bone in bones:
            a = np.array(tuple(rig.matrix_world @ bone.head_local))
            b = np.array(tuple(rig.matrix_world @ bone.tail_local))
            ab = b-a
            t = np.clip(((xyz-a) @ ab)/max(float(ab @ ab),1e-12),0,1)
            distances.append(np.linalg.norm(xyz-(a+t[:,None]*ab),axis=1))
        d = np.array(distances).T
        nearest = np.argsort(d,axis=1)[:,:4]
        ds = np.take_along_axis(d,nearest,axis=1)
        weights = 1/np.maximum(ds,extent*.008)**4
        weights /= weights.sum(axis=1,keepdims=True)
        groups = {b.name:obj.vertex_groups.get(b.name) or obj.vertex_groups.new(name=b.name) for b in bones}
        for g in groups.values():
            try:
                g.remove(list(range(len(obj.data.vertices))))
            except RuntimeError:
                pass
        head = groups['DEF-spine.006']
        for i in range(len(xyz)):
            if 'head_rigid_min_z' in calibration and xyz[i,2]>calibration['head_rigid_min_z']:
                head.add([i],1,'REPLACE')
            else:
                for j,w in zip(nearest[i],weights[i]):
                    groups[bones[j].name].add([i],float(w),'REPLACE')
weighted = total = 0
for obj in meshes:
    deform = {g.index for g in obj.vertex_groups if g.name in rig.data.bones and rig.data.bones[g.name].use_deform}
    total += len(obj.data.vertices)
    weighted += sum(any(g.group in deform and g.weight>0 for g in v.groups) for v in obj.data.vertices)
if total==0 or weighted<.999*total:
    raise RuntimeError(f'{method} skinning incomplete: {weighted}/{total}; no fallback was applied')
for name in ('upper_arm_parent.L','upper_arm_parent.R','thigh_parent.L','thigh_parent.R'):
    if name in rig.pose.bones and 'IK_FK' in rig.pose.bones[name]:
        rig.pose.bones[name]['IK_FK']=1
clip = calibration.get('clip')
scene = bpy.context.scene
if clip:
    scene.frame_start=1
    scene.frame_end=clip['frames']
    scene.render.fps=clip.get('fps',24)
    rig.animation_data_create()
    rig.animation_data.action=bpy.data.actions.new(clip.get('name','CalibratedClip'))
    for name, keyframes in clip['keyframes'].items():
        if name not in rig.pose.bones:
            raise ValueError('unknown Rigify control '+name)
        bone = rig.pose.bones[name]
        bone.rotation_mode='XYZ'
        for frame, rotation in keyframes:
            bone.rotation_euler=rotation
            bone.keyframe_insert('rotation_euler',frame=frame)
output=Path(cfg['output'])
contact_validation={'status':'unavailable','reason':'no explicit contact regions configured'}
if 'contact_checks' in calibration:
    import runpy
    contact=runpy.run_path(str(Path(__file__).with_name('contact.py')))
    contact_validation=contact['evaluate'](meshes,scene,calibration['contact_checks'],clip['frames'] if clip else 1)
    try:
        contact['require_clear'](contact_validation['rows'],contact_validation['margin'])
        contact_validation['status']='pass'
    except ValueError as exc:
        contact_validation.update(status='fail',error=str(exc))
        output.with_suffix('.contact-report.json').write_text(json.dumps(contact_validation,indent=2))
        raise
    output.with_suffix('.contact-report.json').write_text(json.dumps(contact_validation,indent=2))
scene.frame_set(1)
bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(output.with_suffix('.blend')))
# Operators may ignore hidden widget objects; deselect explicitly to prevent export leakage.
for obj in bpy.context.scene.objects:
    obj.select_set(False)
for obj in meshes:
    obj.select_set(True)
rig.select_set(True)
bpy.context.view_layer.objects.active=rig
bpy.ops.export_scene.gltf(use_selection=True,filepath=str(output),export_format='GLB',
    export_skins=True,export_animations=bool(clip),export_def_bones=True,export_frame_range=True)
report={'contact_validation':contact_validation,'skin_method':method,'weighted_vertices':weighted,'vertices':total,
    'triangle_count':sum(len(o.data.polygons) for o in meshes),
    'rig_bones':len(rig.data.bones),'deform_bones':sum(b.use_deform for b in rig.data.bones),
    'finger_bones':False,'calibration':'explicit world coordinates Z-up',
    'geometry_preprocessing':'no decimation or welding',
    'approximate_skinning':method=='capsule','visual_approval':'pending',
    'wall_seconds':round(time.monotonic()-started,2),
    'clip':clip.get('name','CalibratedClip') if clip else None,
    'limitations':['requires manual calibration','basic-human template has no finger chains',
                  'capsule weights do not account for anatomical boundaries or garment layers']}
output.with_suffix('.rig-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('OPENFIGURA_RIG_DONE',flush=True)
