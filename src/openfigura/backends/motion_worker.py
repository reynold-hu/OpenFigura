"""Native retarget baking and regional contact correction; no hand-authored poses."""
import bpy,json,math,runpy,sys
import numpy as np
from pathlib import Path
from mathutils import Matrix,Vector
from mathutils.bvhtree import BVHTree
MARGIN=.002
def pressure(crossings,distance,margin,extent):
 """Steering magnitude: deeper intersection pushes harder; sub-margin proximity gets shortfall plus slack."""
 if crossings:return extent*(.01+.04*min(1.0,crossings/300.0))
 if distance is None or not math.isfinite(distance):return 0.0
 if distance>=margin:return 0.0
 return max(0.0,min(extent*.02,margin-distance+extent*.002))
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
hand_vertices={side:sorted({int(x) for face in faces for x in face}) for side,faces in hand_faces.items()}
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
def pose_vertices():
 dg=bpy.context.evaluated_depsgraph_get();ev=mesh.evaluated_get(dg);data=ev.to_mesh();verts=[ev.matrix_world@v.co for v in data.vertices];ev.to_mesh_clear();return verts
def hand_measure(verts,side,bodytree):
 handtree=BVHTree.FromPolygons(verts,hand_faces[side],all_triangles=True);cross=len(bodytree.overlap(handtree))
 distances=[]
 for i in hand_vertices[side]:
  hit=bodytree.find_nearest(verts[i]);distances.append(hit[3] if hit and hit[0] is not None else math.inf)
 return cross,(min(distances) if distances else math.inf)
for f in range(1,len(frames)+1):
 scene.frame_set(f);bpy.context.view_layer.update();changes=0;initial={}
 for iteration in range(20):
  vertices=pose_vertices();extent=max(v.z for v in vertices)-min(v.z for v in vertices)
  bodytree=BVHTree.FromPolygons(vertices,body_faces,all_triangles=True);acted=False
  for side in hand_faces:
   cross,dist=hand_measure(vertices,side,bodytree)
   if iteration==0:initial[side]={'crossings':cross,'distance':dist if math.isfinite(dist) else None}
   amount=pressure(cross,dist if math.isfinite(dist) else None,MARGIN,extent)
   if amount<=0:continue
   hit=None;best_near=None
   for i in hand_vertices[side]:
    h=bodytree.find_nearest(vertices[i])
    if h and h[0] is not None and (best_near is None or h[3]<best_near[1]):hit=(i,h);best_near=(i,h[3])
   candidates=[]
   if hit and hit[1][1] and hit[1][1].length>=1e-8:candidates.append(hit[1][1].normalized())
   if cross:
    tree=BVHTree.FromPolygons(vertices,hand_faces[side],all_triangles=True)
    acc=Vector((0,0,0))
    for a,b in bodytree.overlap(tree):
      p,q,r=[vertices[j] for j in body_faces[a]];acc+=(q-p).cross(r-p).normalized()
    if acc.length>=1e-8:candidates.append(acc.normalized())
   if hit:
    sep=vertices[hit[0]]-hit[1][0]
    if sep.length>=1e-8:candidates.append(sep.normalized())
   if hand_vertices[side]:
    hc=Vector((0,0,0))
    for i in hand_vertices[side]:hc+=vertices[i]
    hc/=len(hand_vertices[side])
    away=hc-(rig.matrix_world@rig.pose.bones['mixamorig:Hips'].head)
    if away.length>=1e-8:candidates.append(away.normalized())
   scored=[];seen=[]
   for d in candidates:
    if any(abs(d.dot(p)-1.0)<1e-6 for p in seen):continue
    seen.append(d)
    targets[side].location=targets[side].location+d*amount;bpy.context.view_layer.update()
    tv=pose_vertices();ttree=BVHTree.FromPolygons(tv,body_faces,all_triangles=True);tc,td=hand_measure(tv,side,ttree)
    targets[side].location=targets[side].location-d*amount;bpy.context.view_layer.update()
    scored.append(((tc,-td),d))
   if scored:
    best=min(scored,key=lambda s:s[0])
    if best[0]<(cross,-dist):
     targets[side].location=targets[side].location+best[1]*amount;bpy.context.view_layer.update();changes+=1;acted=True
  if not acted:break
 for side,target in targets.items():target.keyframe_insert('location',frame=f)
 cached.append({b.name:b.matrix.copy() for b in rig.pose.bones});steps.append({'frame':f,'iterations':iteration,'target_updates':changes,'before_correction':initial})
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
config={'margin':MARGIN,'pairs':[{'a':[n for n in rig.data.bones.keys() if n.startswith('mixamorig:'+side+'Hand')],'b':body_names} for side in ['Left','Right']]}
report=contact['evaluate']([mesh],scene,config,len(frames));report['correction']='distance-aware two-bone IK steering: intersected body-triangle normals push through overlaps, body-surface separation pushes sub-margin proximity';report['steps']=steps
try:contact['require_clear'](report['rows'],MARGIN);report['status']='pass'
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
