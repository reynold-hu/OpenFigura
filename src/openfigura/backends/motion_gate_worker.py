"""Blender-only gate: run the shared regional contact check on an animated GLB.

Written by OpenFigura; independent of any motion backend. The pass/fail is
decided by contact.py, the same evaluator the retarget worker uses. The
report always names the checked regions and frames; a verdict of pass or
fail requires that every region-resolved frame cleared both intersection
and margin, otherwise status is 'unavailable' with the reason.
"""
import bpy,json,runpy,sys
from pathlib import Path
cfg=json.loads(Path(sys.argv[-1]).read_text())
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
bpy.ops.import_scene.gltf(filepath=cfg['model'])
scene=bpy.context.scene
report={'model':Path(cfg['model']).name,'visual_approval':'pending','margin':cfg.get('margin',.002)}
try:
    meshes=[o for o in scene.objects if o.type=='MESH' and not o.hide_render and o.visible_get()
            and any(m.type=='ARMATURE' for m in o.modifiers)]
    if len(meshes)!=1:raise ValueError(f'gate needs exactly one skinned mesh; found {len(meshes)}')
    mesh=meshes[0]
    names=sorted(g.name for g in mesh.vertex_groups)
    if cfg.get('regions'):
        a,b=list(cfg['regions']['a']),list(cfg['regions']['b'])
        report['regions']={'a':a,'b':b,'source':'explicit'}
    else:
        a=[n for n in names if n.startswith(('mixamorig:LeftHand','mixamorig:RightHand'))]
        b=[n for n in names if any(n.endswith(e) for e in
           ['Hips','Spine','Spine1','Spine2','Neck','Head','LeftUpLeg','LeftLeg','RightUpLeg','RightLeg'])]
        report['regions']={'a':a,'b':b,'source':'auto-mixamorig'}
    if not a or not b:
        raise ValueError('region naming mismatch; pass explicit regions with deform-group names')
    last=int(cfg.get('last_frame') or scene.frame_end)
    report['frames']=max(1,last-int(scene.frame_start)+1)
    contact=runpy.run_path(str(Path(__file__).with_name('contact.py')))
    result=contact['evaluate']([mesh],scene,{'margin':report['margin'],'pairs':[{'a':a,'b':b}]},last)
    try:
        contact['require_clear'](result['rows'],report['margin']);result['status']='pass'
    except ValueError as exc:
        result.update(status='fail',error=str(exc))
    rows=result['rows']
    bad=[r for r in rows if r['crossings'] or r['minimum_vertex_distance']<report['margin']]
    result['summary']={'rows':len(rows),'crossing_rows':sum(1 for r in rows if r['crossings']),
                       'max_crossings':max((r['crossings'] for r in rows),default=0),
                       'min_distance':min((r['minimum_vertex_distance'] for r in rows),default=None),
                       'first_violation':bad[0]['frame'] if bad else None}
    del result['rows']
    report.update(result)
except Exception as exc:
    report.update(status='unavailable',error=f'{type(exc).__name__}: {exc}')
Path(cfg['report']).write_text(json.dumps(report,indent=2),encoding='utf-8')
print('MOTION_GATE_DONE',flush=True)
