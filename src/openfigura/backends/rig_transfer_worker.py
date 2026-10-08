"""Blender-only worker: transfer skeleton + skin weights from a rigged GLB
onto a static GLB of the same character (original implementation; rest-pose
nearest-surface barycentric blend, up to N influences per vertex)."""
import bpy,json,sys
from pathlib import Path
from mathutils.bvhtree import BVHTree

def blend(a,b,c,u,v,w,limit=4):
    """Interpolate three bone->weight dicts at barycentric (u,v,w).

    Keeps the top `limit` influences and renormalises to sum 1; returns []
    when the interpolated surface carries no weights at all.
    """
    acc={}
    for weights,s in ((a,u),(b,v),(c,w)):
        for bone,value in weights.items():
            acc[bone]=acc.get(bone,0.0)+value*s
    if sum(acc.values())<=0.0:return []
    top=sorted(acc.items(),key=lambda kv:-kv[1])[:limit]
    kept=sum(value for _,value in top)
    return [(bone,value/kept) for bone,value in top]

def barycentric(p,a,b,c):
    v0=b-a;v1=c-a;v2=p-a
    d00=v0.dot(v0);d01=v0.dot(v1);d11=v1.dot(v1);d20=v2.dot(v0);d21=v2.dot(v1)
    den=d00*d11-d01*d01
    if abs(den)<1e-12:return (1/3,1/3,1/3)
    v=(d20*d11-d21*d01)/den;w=(d00*d21-d20*d01)/den
    return (1.0-v-w,v,w)

def main(cfg):
    output=Path(cfg['output']);report_path=Path(cfg['report'])
    target_path=Path(cfg['target']).resolve();source_path=Path(cfg['source']).resolve()
    if output.exists() or report_path.exists():raise ValueError('refusing to overwrite output or report')
    if output.resolve() in (target_path,source_path) or report_path.resolve() in (target_path,source_path):
        raise ValueError('refusing to write over an input file')
    limit=int(cfg['params'].get('max_influences',4))
    ratio=float(cfg['params'].get('refuse_distance_ratio',0.05))
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.gltf(filepath=str(source_path))
    before={o.as_pointer() for o in bpy.data.objects}
    rig=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
    skinned=[o for o in bpy.context.scene.objects if o.type=='MESH'
             and any(m.type=='ARMATURE' for m in o.modifiers)]
    if len(skinned)!=1:raise ValueError(f'source needs exactly one skinned mesh; found {len(skinned)}')
    source=skinned[0]
    if not source.vertex_groups:raise ValueError('source mesh carries no bone groups')
    bpy.ops.import_scene.gltf(filepath=str(target_path))
    new=[o for o in bpy.data.objects if o.as_pointer() not in before]
    if any(o.type=='ARMATURE' for o in new) or any(o.type=='MESH' and any(m.type=='ARMATURE' for m in o.modifiers) for o in new):
        raise ValueError('target must be a static unrigged mesh; run on a fresh model')
    targets=[o for o in new if o.type=='MESH' and not o.hide_render and o.visible_get()]
    if len(targets)!=1:raise ValueError(f'target file needs exactly one visible mesh; found {len(targets)}')
    target=targets[0]
    names={g.index:g.name for g in source.vertex_groups}
    source_weights=[{names[g.group]:g.weight for g in v.groups} for v in source.data.vertices]
    sverts=[v.co.copy() for v in source.data.vertices]
    stris=[tuple(p.vertices) for p in source.data.polygons]
    tree=BVHTree.FromPolygons(sverts,stris,all_triangles=True)
    transform=source.matrix_world.inverted()@target.matrix_world
    diagonal=max((source.bound_box[6][i]-source.bound_box[0][i])for i in range(3)) or 1.0
    tverts=[v.co.copy() for v in target.data.vertices]
    tris=[tuple(p.vertices) for p in target.data.polygons]
    tree_t=BVHTree.FromPolygons(tverts,tris,all_triangles=True)
    reverse=target.matrix_world.inverted()@source.matrix_world
    stride=max(1,len(sverts)//200)
    distances=[tree_t.find_nearest(reverse@co)[3] for co in sverts[::stride]]
    median=sorted(distances)[len(distances)//2]
    if median>ratio*diagonal:
        raise ValueError(f'source and target do not overlap in rest pose (median sample distance {median:.5f} > {ratio} x diagonal {diagonal:.3f}); align or scale them first')
    needed={bone for d in source_weights for bone in d}
    groups={name:target.vertex_groups.new(name=name) for name in needed}
    deviations=[]
    empty=0
    polys=source.data.polygons
    for vertex in target.data.vertices:
        co=transform@vertex.co
        hit=tree.find_nearest(co)
        if hit[0] is None:raise ValueError('no surface under target vertex '+str(co))
        poly=polys[hit[2]]
        ids=poly.vertices
        u,v,w=barycentric(hit[0],source.data.vertices[ids[0]].co,source.data.vertices[ids[1]].co,source.data.vertices[ids[2]].co)
        top=blend(source_weights[ids[0]],source_weights[ids[1]],source_weights[ids[2]],u,v,w,limit)
        if not top:empty+=1
        for bone,weight in top:
            groups[bone].add([vertex.index],weight,'REPLACE')
        deviations.append(hit[3])
    target.parent=rig
    target.matrix_parent_inverse=rig.matrix_world.inverted()
    modifier=target.modifiers.new('OpenFiguraRigTransfer','ARMATURE');modifier.object=rig
    bpy.ops.object.select_all(action='DESELECT')
    target.select_set(True);rig.select_set(True);bpy.context.view_layer.objects.active=rig
    bpy.ops.export_scene.gltf(filepath=str(output),export_format='GLB',use_selection=True,
                              export_skins=True,export_animations=False,export_yup=True)
    deviations.sort()
    report={'method':'rest-pose nearest-triangle barycentric weight blend, top-N influences renormalised',
            'max_influences':limit,'joints':len(rig.data.bones),'vertex_groups':len(target.vertex_groups),
            'vertices':len(target.data.vertices),'vertices_without_weights':empty,
            'distance_to_source_surface':{'mean':sum(deviations)/len(deviations),
              'median':deviations[len(deviations)//2],'p95':deviations[int(len(deviations)*0.95)],'max':deviations[-1],
              'units':'object-local; nearest source surface, one-way'},
            'overlap_guard':{'median_sample_distance':median,'refuse_threshold':ratio*diagonal},
            'warning':'Weights follow the nearest source surface only: no correspondence learning, no deformation test; verify posed renders before shipping.',
            'visual_approval':'pending','output':str(output)}
    report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('RIG_TRANSFER_DONE',flush=True)

if __name__=='__main__':
    main(json.loads(Path(sys.argv[-1]).read_text(encoding='utf-8')))
