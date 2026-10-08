"""Blender-only multi-format export worker: FBX/OBJ/STL/USD from a verified GLB."""
import addon_utils,bpy,json,sys
from pathlib import Path
cfg=json.loads(Path(sys.argv[-1]).read_text());fmt=cfg['format']
out=Path(cfg['output']);rp=Path(cfg['report'])
if out.exists() or rp.exists() or out.resolve()==Path(cfg['model']).resolve():
    raise ValueError('refusing to overwrite output, report, or source')
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
bpy.ops.import_scene.gltf(filepath=cfg['model'])
objs=[o for o in bpy.context.scene.objects if not o.hide_render and o.visible_get()]
meshes=[o for o in objs if o.type=='MESH']
source={'objects':len(objs),'meshes':len(meshes),
        'vertices':sum(len(o.data.vertices) for o in meshes),
        'materials':sorted({m.name for o in meshes for m in o.data.materials if m}),
        'actions':sorted(a.name for a in bpy.data.actions)}
warnings=[]
if fmt=='fbx':
    addon_utils.enable('io_scene_fbx',default_set=False)
    bpy.ops.export_scene.fbx(filepath=str(out),object_types={'ARMATURE','MESH'},
                             bake_anim=True,add_leaf_bones=False,
                             path_mode='COPY',embed_textures=True)
    warnings.append('FBX carries armature+skin+sampled animation; cameras/lights dropped; textures embedded.')
elif fmt=='obj':
    bpy.ops.wm.obj_export(filepath=str(out))
    warnings.append('OBJ is static evaluated geometry plus a material library: skin weights, animation and PBR links are not carried.')
elif fmt=='stl':
    addon_utils.enable('io_mesh_stl',default_set=False)
    bpy.ops.wm.stl_export(filepath=str(out))
    warnings.append('STL is a single static mesh: no materials, skins or animation; units follow the source scale.')
elif fmt=='usd':
    bpy.ops.wm.usd_export(filepath=str(out))
    warnings.append('USD export in Blender skinned-animation support is limited; verify deformation in the target DCC before shipping.')
else:
    raise ValueError('unsupported format')
report={'format':fmt,'source':source,'warnings':warnings,'bytes':out.stat().st_size,
        'axis':'Blender Z-up conversion handled by each exporter',
        'visual_approval':'pending'}
rp.write_text(json.dumps(report,indent=2),encoding='utf-8')
print('FORMAT_DONE',flush=True)
