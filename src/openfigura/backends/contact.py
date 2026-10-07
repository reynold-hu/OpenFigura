"""Explicit regional surface checks, not a physics or cloth solver."""
import math

def validate_config(config):
    if not isinstance(config, dict) or not isinstance(config.get('pairs'), list) or not config['pairs']:
        raise ValueError('contact_checks needs nonempty pairs')
    margin = config.get('margin', 0.002)
    if not isinstance(margin, (int, float)) or not math.isfinite(margin) or margin < 0:
        raise ValueError('contact margin must be finite and nonnegative')
    for pair in config['pairs']:
        if not isinstance(pair, dict):
            raise ValueError('contact pair must be an object')
        for key in ('a', 'b'):
            if not isinstance(pair.get(key), list) or not pair[key] or not all(isinstance(x,str) and x for x in pair[key]):
                raise ValueError('contact regions need explicit deform-group names')
        if set(pair['a']) & set(pair['b']):
            raise ValueError('contact regions must be disjoint')

def require_clear(rows, margin):
    if not rows:
        raise ValueError('no contact frames were checked')
    for row in rows:
        if row['crossings']:
            raise ValueError(f"surface intersection at frame {row['frame']}: {row['pair']}")
        distance = row['minimum_vertex_distance']
        if distance is None or not math.isfinite(distance) or distance < margin:
            raise ValueError(f"insufficient clearance at frame {row['frame']}: {row['pair']}")

def evaluate(meshes, scene, config, last_frame):
    """Check all integer frames, evaluated world surfaces selected by dominant weight.

    This excludes transition triangles and does not prove containment-free closed
    volumes or continuous-time clearance. All region-A vertices are distance tested.
    """
    import bpy
    import numpy as np
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    validate_config(config)
    selections = []
    for obj in meshes:
        labels = []
        for v in obj.data.vertices:
            group = max(v.groups, key=lambda g:g.weight) if v.groups else None
            labels.append(obj.vertex_groups[group.group].name if group else '')
        labels = np.array(labels)
        obj.data.calc_loop_triangles()
        triangles = np.array([tuple(t.vertices) for t in obj.data.loop_triangles])
        regions = []
        for pair in config['pairs']:
            entries = []
            for side in ('a','b'):
                faces = triangles[np.all(np.isin(labels[triangles], pair[side]), axis=1)]
                ids = np.unique(faces)
                mapping = np.full(len(labels), -1); mapping[ids] = np.arange(len(ids))
                entries.append((ids, mapping[faces]))
            regions.append(entries)
        selections.append((obj, regions))
    rows = []
    for frame in range(1, last_frame+1):
        scene.frame_set(frame); bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        buffers = [[([],[]),([],[])] for _ in config['pairs']]
        for obj, regions in selections:
            ev = obj.evaluated_get(dg); mesh = ev.to_mesh()
            try:
                if len(mesh.vertices) != len(obj.data.vertices):
                    raise ValueError('contact checks require topology-preserving deformation')
                for p, entries in enumerate(regions):
                    for side, (ids, faces) in enumerate(entries):
                        vertices, polygons = buffers[p][side]; offset = len(vertices)
                        vertices.extend(tuple(ev.matrix_world @ mesh.vertices[int(i)].co) for i in ids)
                        polygons.extend((faces+offset).tolist())
            finally:
                ev.to_mesh_clear()
        for p, pair in enumerate(config['pairs']):
            a,b = buffers[p]
            if not a[1] or not b[1]:
                raise ValueError('empty contact region: '+str(pair))
            ta = BVHTree.FromPolygons(a[0],a[1],all_triangles=True)
            tb = BVHTree.FromPolygons(b[0],b[1],all_triangles=True)
            distance = min(tb.find_nearest(Vector(v))[3] for v in a[0])
            rows.append({'frame':frame,'pair':'/'.join([','.join(pair['a']),','.join(pair['b'])]),
                         'crossings':len(ta.overlap(tb)), 'minimum_vertex_distance':distance})
    return {'status':'checked','method':'dominant-weight regional triangle BVH + all A-vertex clearance',
            'margin':config.get('margin',.002),'frames':last_frame,'rows':rows,
            'limitations':['transition triangles excluded','no closed-volume containment proof',
                          'integer frames only','not cloth physics or automatic correction']}
