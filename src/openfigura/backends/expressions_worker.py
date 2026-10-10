"""Blender-only worker: write ARKit-named morph targets onto a character mesh.

Receives a compact npz payload (aligned hm08 base + per-channel world-space
delta fields) and, for each channel, adds a shape key whose data is the
nearest-sampled field with a Gaussian falloff. The exported GLB therefore
carries real, individually scrubable morph targets — the photo's blendshape
scores are applied as weights, not baked away.
"""
import bpy,json,sys
import numpy as np
from pathlib import Path
cfg=json.loads(Path(sys.argv[-1]).read_text())
out=Path(cfg['output']);report_path=Path(cfg['report'])
if out.exists() or report_path.exists():raise ValueError('refusing to overwrite output or report')
payload=np.load(cfg['payload'])
base_al=payload['base_al']
channels=[str(c) for c in payload['channels']]
fields=payload['fields']
scores=payload['scores']
sigma=float(payload['sigma'])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
bpy.ops.import_scene.gltf(filepath=cfg['model'])
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH' and not o.hide_render and o.visible_get()]
if len(meshes)!=1:raise ValueError(f'needs exactly one visible mesh; found {len(meshes)}')
mesh=meshes[0]
mw=np.array(mesh.matrix_world);mwi=np.linalg.inv(mw)
raw=np.empty(len(mesh.data.vertices)*3,dtype=np.float32)
mesh.data.vertices.foreach_get('co',raw)
local=raw.reshape(-1,3).astype(np.float64)
world=local@mw[:3,:3].T+mw[:3,3]
offsets=np.zeros((len(world),len(channels),3),dtype=np.float64)
max_offsets=[]
for start in range(0,len(world),4000):
    chunk=world[start:start+4000]
    d2=((chunk[:,None,:]-base_al[None,:,:])**2).sum(axis=2)
    nn=d2.argmin(axis=1)
    falloff=np.exp(-d2[np.arange(len(chunk)),nn]/sigma**2)
    offsets[start:start+4000]=(fields[:,nn].transpose(1,0,2)*falloff[:,None,None])
    max_offsets.append(np.abs(offsets[start:start+4000]).max())
if mesh.data.shape_keys is None:
    mesh.shape_key_add(name='Basis',from_mix=False)
basis=mesh.data.shape_keys.key_blocks['Basis']
written=[]
for index,channel in enumerate(channels):
    key=mesh.shape_key_add(name=channel,from_mix=False)
    displaced_world=world+offsets[:,index]
    displaced_local=displaced_world@mwi[:3,:3].T+mwi[:3,3]
    key.data.foreach_set('co',displaced_local.astype(np.float32).ravel())
    key.value=float(scores[index])
    written.append({'channel':channel,'score':float(scores[index]),
                    'max_displacement':float(np.abs(offsets[:,index]).max())})
bpy.ops.object.select_all(action='DESELECT')
mesh.select_set(True);bpy.context.view_layer.objects.active=mesh
bpy.ops.export_scene.gltf(filepath=str(out),export_format='GLB',use_selection=True,
                          export_morph=True,export_yup=True)
report={'model':Path(cfg['model']).name,'vertices':int(len(world)),'base_reference':int(len(base_al)),
        'morph_targets':written,'weights_applied':{w['channel']:w['score'] for w in written},
        'falloff_sigma':sigma,'output':str(out),'visual_approval':'pending'}
report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
print('EXPRESSIONS_DONE',flush=True)
