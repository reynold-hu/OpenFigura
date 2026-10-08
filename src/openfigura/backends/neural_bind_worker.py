"""Bind predicted MIA results to original Blender geometry, no manual fitting."""
import bpy,json,sys,time
from pathlib import Path
import numpy as np
from mathutils import Vector
from mathutils.kdtree import KDTree
cfg=json.loads(Path(sys.argv[-1]).read_text());root=Path(cfg['native']);started=time.monotonic()
skeleton=json.loads((root/'skeleton.json').read_text());names=skeleton['names'];heads=np.array(skeleton['heads']);tails=np.array(skeleton['tails']);parents=skeleton['parents']
weights=np.load(root/'weights.npy',mmap_mode='r');vertices=np.load(root/'vertices.npy')
if heads.shape!=(len(names),3) or tails.shape!=heads.shape or len(parents)!=len(names) or len(set(names))!=len(names):raise ValueError('invalid neural skeleton shape')
if not np.isfinite(heads).all() or not np.isfinite(tails).all() or np.any(np.linalg.norm(heads-tails,axis=1)<1e-6):raise ValueError('nonfinite/degenerate predicted bones')
if weights.shape!=(len(vertices),len(names)) or not np.isfinite(weights).all() or np.any(weights<0) or not np.allclose(weights.sum(1),1,atol=1e-4):raise ValueError('invalid neural weights')
# glTF world Y-up -> Blender world Z-up; original geometry is not regenerated.
def to_blender(p):return Vector((float(p[0]),float(-p[2]),float(p[1])))
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete();bpy.ops.import_scene.gltf(filepath=cfg['model'])
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH' and not o.hide_render and o.visible_get()]
arm=bpy.data.armatures.new('MIA_PredictedSkeleton');rig=bpy.data.objects.new('MIA_PredictedSkeleton',arm);bpy.context.collection.objects.link(rig);bpy.context.view_layer.objects.active=rig;rig.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
for name,h,t in zip(names,heads,tails):
 b=arm.edit_bones.new(name);b.head=to_blender(h);b.tail=to_blender(t)
for i,p in enumerate(parents):
 if type(p) is not int or p>=i or p< -1:raise ValueError('invalid skeleton parent order')
 if p>=0:arm.edit_bones[names[i]].parent=arm.edit_bones[names[p]]
bpy.ops.object.mode_set(mode='OBJECT');rig.show_in_front=True
kd=KDTree(len(vertices))
for i,p in enumerate(vertices):kd.insert(to_blender(p),i)
kd.balance();extent=float(np.ptp(vertices,axis=0).max());max_error=0;mass_sum=0;count=0
for obj in meshes:
 groups=[obj.vertex_groups.new(name=n) for n in names]
 for v in obj.data.vertices:
  _,index,error=kd.find(obj.matrix_world@v.co);max_error=max(max_error,error)
  if error>extent*1e-4:raise ValueError('neural/source vertex coordinate mismatch')
  row=weights[index];idx=np.argsort(row)[-4:];mass=float(row[idx].sum())
  if mass<=0:raise ValueError('zero skin mass')
  mass_sum+=mass;count+=1
  for j in idx:groups[int(j)].add([v.index],float(row[j]/mass),'REPLACE')
 world=obj.matrix_world.copy();obj.parent=rig;obj.matrix_world=world
 mod=obj.modifiers.new('MIA_NeuralSkin','ARMATURE');mod.object=rig
for o in bpy.context.scene.objects:o.select_set(False)
for o in meshes:o.select_set(True)
rig.select_set(True);bpy.context.view_layer.objects.active=rig
output=Path(cfg['output']);bpy.ops.wm.save_as_mainfile(filepath=str(output.with_suffix('.blend')))
bpy.ops.export_scene.gltf(filepath=str(output),use_selection=True,export_format='GLB',export_skins=True,export_animations=False,export_def_bones=True)
report={'bones':len(names),'weighted_vertices':count,'max_vertex_mapping_error':max_error,'mean_retained_top4_weight_mass':mass_sum/count,'geometry':'original GLB meshes; no decimation/welding','manual_coordinates':False,'source_coordinates':'glTF Y-up; converted to Blender Z-up','static_rig':True,'visual_approval':'pending','wall_seconds':round(time.monotonic()-started,2)}
output.with_suffix('.bind-report.json').write_text(json.dumps(report,indent=2));print('NEURAL_BIND_DONE',flush=True)
