"""Native retarget baking and regional contact correction; no hand-authored poses."""
import bpy,json,math,runpy,sys
import numpy as np
from pathlib import Path
from mathutils import Matrix,Vector
from mathutils.bvhtree import BVHTree
cfg=json.loads(Path(sys.argv[-1]).read_text());root=Path(cfg['native']);capture=root
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete();bpy.ops.import_scene.gltf(filepath=cfg['model'])
rig=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE');rest=json.loads((capture/'rest.json').read_text());frames=json.loads((capture/'poses.json').read_text());names=rest['names']
R=Matrix.Rotation(math.pi/2,4,'X')
def world(columns):return R@Matrix(tuple(tuple(columns[j][i] for j in range(4)) for i in range(3))+((0,0,0,1),))
bones={b.name.replace(':','_'):b for b in rig.data.bones};error=0
axis_corrections={}
for name,m in zip(names,rest['rest']):
 if name not in bones:raise ValueError('imported bone name mismatch '+name)
 expected=rig.matrix_world@bones[name].matrix_local;actual=world(m)
 error=max(error,(actual.translation-expected.translation).length)
 axis_corrections[name]=actual.inverted()@expected
if error>1e-4:raise ValueError('rest joint position mismatch')
rig.animation_data_clear();rig.animation_data_create();rig.animation_data.action=bpy.data.actions.new('GodotNativeRetargetRun')
for frame in frames:
 matrices={name:rig.matrix_world.inverted()@world(m)@axis_corrections[name] for name,m in zip(names,frame['poses'])}
 for name,b in bones.items():
  parent=b.parent
  kwargs={'parent_matrix':matrices[parent.name.replace(':','_')],'parent_matrix_local':parent.matrix_local} if parent else {}
  pb=rig.pose.bones[b.name];pb.rotation_mode='QUATERNION';pb.matrix_basis=b.convert_local_to_pose(matrices[name],b.matrix_local,invert=True,**kwargs)
  for prop in ('location','rotation_quaternion','scale'):pb.keyframe_insert(prop,frame=frame['frame'])
scene=bpy.context.scene;scene.frame_start=1;scene.frame_end=len(frames);scene.render.fps=cfg['fps']
skinned_meshes=[o for o in scene.objects if o.type=='MESH' and not o.hide_render and o.visible_get() and any(m.type=='ARMATURE' for m in o.modifiers)]
if len(skinned_meshes)!=1:raise ValueError('native motion currently requires one skinned render mesh')
mesh=skinned_meshes[0]
labels=np.array([mesh.vertex_groups[max(v.groups,key=lambda g:g.weight).group].name for v in mesh.data.vertices])
mesh.data.calc_loop_triangles();tri=np.array([tuple(t.vertices) for t in mesh.data.loop_triangles])
body=np.array([any(n.endswith(x) for x in ['Hips','Spine','Spine1','Spine2','Neck','Head','LeftUpLeg','LeftLeg','RightUpLeg','RightLeg']) for n in labels]);body_faces=tri[np.all(body[tri],axis=1)].tolist()
hand_faces={side:tri[np.all(np.char.startswith(labels[tri],'mixamorig:'+side+'Hand'),axis=1)].tolist() for side in ['Left','Right']}
extent=.0
raw_targets={side:[] for side in hand_faces}
for f in range(1,len(frames)+1):
 scene.frame_set(f);bpy.context.view_layer.update()
 for side in hand_faces:raw_targets[side].append(rig.matrix_world@rig.pose.bones['mixamorig:'+side+'ForeArm'].tail)
targets={}
for side in hand_faces:
 target=bpy.data.objects.new('ContactIK_'+side,None);scene.collection.objects.link(target);targets[side]=target
 for f,p in enumerate(raw_targets[side],1):target.location=p;target.keyframe_insert('location',frame=f)
 con=rig.pose.bones['mixamorig:'+side+'ForeArm'].constraints.new('IK');con.target=target;con.chain_count=2;con.iterations=100;con.use_rotation=False
steps=[];cached=[]
for f in range(1,len(frames)+1):
 scene.frame_set(f);bpy.context.view_layer.update();changes=0
 for iteration in range(12):
  dg=bpy.context.evaluated_depsgraph_get();ev=mesh.evaluated_get(dg);data=ev.to_mesh();vertices=[ev.matrix_world@v.co for v in data.vertices];ev.to_mesh_clear()
  bodytree=BVHTree.FromPolygons(vertices,body_faces,all_triangles=True);overlaps={}
  extent=max(v.z for v in vertices)-min(v.z for v in vertices)
  for side,faces in hand_faces.items():
   handtree=BVHTree.FromPolygons(vertices,faces,all_triangles=True);pairs=bodytree.overlap(handtree)
   if pairs:
    normal=Vector((0,0,0))
    for i in set(a for a,b in pairs):
     a,b,c=[vertices[j] for j in body_faces[i]];normal+=(b-a).cross(c-a).normalized()
    if normal.length<1e-8:raise ValueError('ambiguous contact normal')
    overlaps[side]=normal.normalized()
  if not overlaps:break
  for side,normal in overlaps.items():targets[side].location+=normal*extent*.015;changes+=1
  bpy.context.view_layer.update()
 for side,target in targets.items():target.keyframe_insert('location',frame=f)
 cached.append({b.name:b.matrix.copy() for b in rig.pose.bones});steps.append({'frame':f,'iterations':iteration,'target_updates':changes})
# Bake final evaluated poses into ordinary keys, then remove constraints/targets.
for b in rig.pose.bones:
 for con in list(b.constraints):b.constraints.remove(con)
rig.animation_data.action=bpy.data.actions.new('NativeRetargetIKContactTrial')
for f,poses in enumerate(cached,1):
 for b in rig.data.bones:
  kwargs={'parent_matrix':poses[b.parent.name],'parent_matrix_local':b.parent.matrix_local} if b.parent else {}
  pb=rig.pose.bones[b.name];pb.rotation_mode='QUATERNION';pb.matrix_basis=b.convert_local_to_pose(poses[b.name],b.matrix_local,invert=True,**kwargs)
  for prop in ['location','rotation_quaternion','scale']:pb.keyframe_insert(prop,frame=f)
contact=runpy.run_path(str(Path(__file__).with_name('contact.py')))
body_names=[n for n in rig.data.bones.keys() if any(n.endswith(x) for x in ['Hips','Spine','Spine1','Spine2','Neck','Head','LeftUpLeg','LeftLeg','RightUpLeg','RightLeg'])]
config={'margin':.002,'pairs':[{'a':[n for n in rig.data.bones.keys() if n.startswith('mixamorig:'+side+'Hand')],'b':body_names} for side in ['Left','Right']]}
report=contact['evaluate']([mesh],scene,config,len(frames));report['correction']='Blender native two-bone IK with BVH intersected body triangle normal steering';report['steps']=steps
try:contact['require_clear'](report['rows'],.002);report['status']='pass'
except ValueError as e:report.update(status='fail',error=str(e))
(root/'contact-report.json').write_text(json.dumps(report,indent=2));scene.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=str(root/'diagnostic.blend'))
if report['status']!='pass':raise ValueError('IK diagnostic rejected: '+report['error'])
for o in scene.objects:o.select_set(False)
mesh.select_set(True);rig.select_set(True);bpy.context.view_layer.objects.active=rig
active_action=rig.animation_data.action
for action in list(bpy.data.actions):
 if action!=active_action:bpy.data.actions.remove(action)
output=Path(cfg['output']);bpy.ops.wm.save_as_mainfile(filepath=str(output.with_suffix('.blend')))
bpy.ops.export_scene.gltf(filepath=str(output),use_selection=True,export_format='GLB',export_skins=True,export_animations=True,export_def_bones=True,export_frame_range=True)
print('MOTION_DONE',flush=True)
