import ast
import math
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest
from openfigura.backends.mesh_tools import MeshToolsBackend


def helpers():
    worker = Path(__file__).parents[1] / 'src/openfigura/backends/mesh_tools_worker.py'
    names = {'exact_topology_metrics', 'require_topology_nonregression'}
    nodes = [n for n in ast.parse(worker.read_text()).body
             if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(nodes) == 2, 'exact-position topology measurement and rejection gate required'
    ns = {'Counter': Counter, 'math': math}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(worker), 'exec'), ns)
    return ns


def tetra():
    return [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)], [(0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)]


def test_uv_split_closed_tetra_has_no_geometric_boundaries():
    ns = helpers(); vertices, faces = tetra()
    corners = [vertices[v] for face in faces for v in face]
    split_faces = [tuple(range(i, i+3)) for i in range(0, 12, 3)]
    metrics = ns['exact_topology_metrics'](corners, split_faces)
    assert metrics['boundary_edges'] == metrics['nonmanifold_edges'] == 0
    assert metrics['duplicate_position_vertices'] == 8
    assert metrics['position_clusters'] == 4


def test_open_tetra_rejected_against_closed_prepared_geometry():
    ns = helpers(); vertices, faces = tetra()
    before = ns['exact_topology_metrics'](vertices, faces)
    after = ns['exact_topology_metrics'](vertices, faces[:-1])
    assert after['boundary_edges'] == 3
    with pytest.raises(ValueError, match='boundary_edges'):
        ns['require_topology_nonregression'](before, after)


def test_duplicate_degenerate_and_nonmanifold_counts_are_not_hidden():
    ns = helpers(); vertices, faces = tetra()
    before = ns['exact_topology_metrics'](vertices, faces)
    after = ns['exact_topology_metrics'](vertices, faces + [faces[0], (0, 0, 1)])
    assert after['duplicate_faces'] == 1
    assert after['degenerate_faces'] == 1
    assert after['nonmanifold_edges'] == 3
    with pytest.raises(ValueError, match='duplicate_faces'):
        ns['require_topology_nonregression'](before, after)
    ns['require_topology_nonregression'](after, after)


def test_collinear_triangle_is_degenerate_without_distance_tolerance():
    ns = helpers()
    metrics = ns['exact_topology_metrics']([(0,0,0),(1,0,0),(2,0,0)], [(0,1,2)])
    assert metrics['degenerate_faces'] == 1
    tiny = ns['exact_topology_metrics']([(0,0,0),(1,0,0),(0,1e-15,0)], [(0,1,2)])
    assert tiny['degenerate_faces'] == 0


@pytest.mark.parametrize('value', [None, 0, 1, 'false', [], {}])
def test_weld_seams_requires_boolean_before_binary_probe(tmp_path, monkeypatch, value):
    source = tmp_path/'source.glb'; source.write_bytes(b'fixture')
    def probe(self):
        pytest.fail('invalid weld_seams reached binary probe')
    monkeypatch.setattr(MeshToolsBackend, 'binary', probe)
    with pytest.raises(ValueError, match='weld_seams'):
        MeshToolsBackend().process(source, tmp_path/'out.glb', 'optimize', {'ratio': .08, 'weld_seams': value})


@pytest.mark.parametrize('setting', ['default', True, False])
def test_weld_seams_default_and_false_sent_to_worker(tmp_path, monkeypatch, setting):
    source = tmp_path/'source.glb'; source.write_bytes(b'fixture')
    params = {'ratio': .08}
    if setting != 'default': params['weld_seams'] = setting
    def run(argv, **kwargs):
        import json
        cfg = json.loads(Path(argv[-1]).read_text())
        assert cfg['params']['weld_seams'] is (setting != False)
        return SimpleNamespace(returncode=1, stdout='', stderr='rejected topology')
    monkeypatch.setattr(MeshToolsBackend, 'binary', lambda self: '/fake/blender')
    monkeypatch.setattr('openfigura.backends.mesh_tools.subprocess.run', run)
    result = MeshToolsBackend().process(source, tmp_path/'out.glb', 'optimize', params)
    assert result['exit_code'] == 1
    assert not (tmp_path/'out.glb').exists()


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf')])
def test_nonfinite_positions_are_rejected_even_without_count_growth(value):
    ns = helpers()
    metrics = ns['exact_topology_metrics']([(0,0,0),(1,0,0),(0,value,0)], [(0,1,2)])
    assert metrics['nonfinite_positions'] == 1
    with pytest.raises(ValueError, match='nonfinite'):
        ns['require_topology_nonregression'](metrics, metrics)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf')])
def test_nonfinite_uv_is_rejected_independently_of_topology(value):
    ns = helpers(); vertices, faces = tetra()
    metrics = ns['exact_topology_metrics'](vertices, faces)
    metrics['nonfinite_uv_corners'] = int(not math.isfinite(value))
    with pytest.raises(ValueError, match='nonfinite_uv_corners'):
        ns['require_topology_nonregression'](metrics, metrics)


def worker_main_namespace(tmp_path, mesh_count=1):
    import json
    worker = Path(__file__).parents[1] / 'src/openfigura/backends/mesh_tools_worker.py'
    main = [n for n in ast.parse(worker.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == 'main']
    shared = SimpleNamespace(users=mesh_count, shape_keys=None)
    shared.copy = lambda: SimpleNamespace(users=1, shape_keys=None)
    class Modifiers(list):
        def new(self, *args): return SimpleNamespace(name='Decimate')
    objects = [SimpleNamespace(name=str(i), data=shared, type='MESH', animation_data=None, modifiers=Modifiers(), select_set=lambda *a:None) for i in range(mesh_count)]
    noop = lambda **kwargs: None
    exported = []
    def export(**kwargs):
        exported.append(kwargs); Path(kwargs['filepath']).write_bytes(b'glb')
    bpy = SimpleNamespace(context=SimpleNamespace(scene=SimpleNamespace(objects=objects)),
                          ops=SimpleNamespace(object=SimpleNamespace(select_all=noop, delete=noop, modifier_apply=noop), import_scene=SimpleNamespace(gltf=noop), export_scene=SimpleNamespace(gltf=export)))
    metric = {'vertices':4, 'faces':4, 'triangles':4, 'boundary_edges':0,'nonmanifold_edges':0,'duplicate_faces':0,'degenerate_faces':0,'nonfinite_positions':0,'nonfinite_uv_corners':0,'bbox_local':[[0,0,0],[1,1,1]]}
    ns = {'Path':Path, 'json':json, 'glb_nonfinite_metrics':lambda path:{}, 'bpy':bpy, 'meshes':lambda:objects,'stats':lambda objs:{'objects':len(objs)},'activate':lambda obj:None,'mesh_topology':lambda obj:dict(metric),**helpers()}
    exec(compile(ast.Module(body=main, type_ignores=[]), str(worker), 'exec'), ns)
    cfg = {'output':str(tmp_path/'out.glb'),'report':str(tmp_path/'report.json'),'model':str(tmp_path/'in.glb'),'operation':'optimize','params':{'ratio':.5,'weld_seams':False}}
    return ns, cfg, objects, exported


def test_blender_runtime_error_retains_rejection_diagnostic(tmp_path):
    import json
    ns,cfg,objects,exported = worker_main_namespace(tmp_path)
    def fail(obj): raise RuntimeError('Blender API failure')
    ns['mesh_topology'] = fail
    with pytest.raises(RuntimeError, match='Blender API failure'):
        ns['main'](cfg)
    report = Path(cfg['report'])
    assert report.exists(), 'Blender runtime failure must retain diagnostic before re-raising'
    assert json.loads(report.read_text())['status'] == 'rejected'
    assert not exported


def test_shared_mesh_instances_are_isolated_before_modification(tmp_path):
    ns,cfg,objects,exported = worker_main_namespace(tmp_path,2)
    shared = objects[0].data
    def check(obj):
        assert obj.data is not shared and obj.data.users == 1
        return {'vertices':4,'faces':4,'triangles':4,'boundary_edges':0,'nonmanifold_edges':0,'duplicate_faces':0,'degenerate_faces':0,'nonfinite_positions':0,'nonfinite_uv_corners':0,'bbox_local':[[0,0,0],[1,1,1]]}
    ns['mesh_topology']=check
    ns['main'](cfg)
    assert objects[0].data is not objects[1].data
    assert exported


@pytest.mark.parametrize('semantic,value', [('POSITION',float('nan')),('POSITION',float('inf')),('TEXCOORD_0',float('nan')),('TEXCOORD_0',float('inf'))])
def test_encoded_nonfinite_glb_rejected_before_blender_can_sanitize(tmp_path, semantic, value):
    import json, struct
    worker=Path(__file__).parents[1]/'src/openfigura/backends/mesh_tools_worker.py'
    nodes=[n for n in ast.parse(worker.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='glb_nonfinite_metrics']
    assert nodes, 'encoded GLB preflight must precede Blender numeric sanitization'
    ns={'Path':Path,'json':json,'struct':struct,'math':math}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(worker),'exec'),ns)
    doc={'buffers':[{'byteLength':12}],'bufferViews':[{'buffer':0,'byteLength':12}],'accessors':[{'bufferView':0,'componentType':5126,'count':1,'type':'VEC3'}],'meshes':[{'primitives':[{'attributes':{semantic:0}}]}]}
    chunk=json.dumps(doc).encode();chunk+=b' '*((-len(chunk))%4);binary=struct.pack('<fff',value,0,0)
    data=struct.pack('<III',0x46546c67,2,12+8+len(chunk)+8+len(binary))+struct.pack('<II',len(chunk),0x4e4f534a)+chunk+struct.pack('<II',len(binary),0x004e4942)+binary
    source=tmp_path/'nonfinite.glb';source.write_bytes(data)
    metrics=ns['glb_nonfinite_metrics'](source)
    key='nonfinite_positions' if semantic=='POSITION' else 'nonfinite_uv_corners'
    assert metrics[key]==1
    with pytest.raises(ValueError,match=key): helpers()['require_topology_nonregression'](metrics,metrics)


def encoded_fixture(tmp_path, overrides=None, extensions=None):
    import json,struct
    worker=Path(__file__).parents[1]/'src/openfigura/backends/mesh_tools_worker.py'
    nodes=[n for n in ast.parse(worker.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='glb_nonfinite_metrics']
    ns={'Path':Path,'json':json,'struct':struct,'math':math}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(worker),'exec'),ns)
    doc={'buffers':[{'byteLength':12}],'bufferViews':[{'buffer':0,'byteLength':12}],'accessors':[{'bufferView':0,'componentType':5126,'count':1,'type':'VEC3'}],'meshes':[{'primitives':[{'attributes':{'POSITION':0}}]}]}
    if overrides:
        for key,value in overrides.items():doc[key]=value
    if extensions: doc['meshes'][0]['primitives'][0]['extensions']=extensions
    chunk=json.dumps(doc).encode();chunk+=b' '*((-len(chunk))%4);binary=struct.pack('<fff',0,0,0)
    data=struct.pack('<III',0x46546c67,2,12+8+len(chunk)+8+len(binary))+struct.pack('<II',len(chunk),0x4e4f534a)+chunk+struct.pack('<II',len(binary),0x004e4942)+binary
    source=tmp_path/'fixture.glb';source.write_bytes(data)
    return ns['glb_nonfinite_metrics'],source


@pytest.mark.parametrize('view', [{'buffer':0,'byteLength':12,'byteOffset':-4},{'buffer':0,'byteLength':16},{'buffer':0,'byteLength':12,'byteStride':8}])
def test_numeric_preflight_rejects_invalid_view_and_stride_bounds(tmp_path,view):
    measure,source=encoded_fixture(tmp_path,{'bufferViews':[view]})
    with pytest.raises(ValueError): measure(source)


def test_numeric_preflight_explicitly_rejects_compressed_coverage(tmp_path):
    measure,source=encoded_fixture(tmp_path,extensions={'KHR_draco_mesh_compression':{'bufferView':0,'attributes':{'POSITION':0}}})
    with pytest.raises(ValueError,match='compressed'):measure(source)


@pytest.mark.parametrize('accessor', [{'bufferView':0,'componentType':5126,'count':1,'type':'VEC3','byteOffset':-4},{'bufferView':0,'componentType':5126,'count':2,'type':'VEC3'},{'bufferView':-1,'componentType':5126,'count':1,'type':'VEC3'}])
def test_numeric_preflight_rejects_invalid_accessor_offsets_count_and_index(tmp_path,accessor):
    measure,source=encoded_fixture(tmp_path,{'accessors':[accessor]})
    with pytest.raises(ValueError):measure(source)


def test_numeric_preflight_checks_sparse_float_values(tmp_path):
    import struct
    accessor={'componentType':5126,'count':1,'type':'VEC3','sparse':{'count':1,'values':{'bufferView':0},'indices':{'bufferView':0,'componentType':5121}}}
    measure,source=encoded_fixture(tmp_path,{'accessors':[accessor]})
    data=bytearray(source.read_bytes());struct.pack_into('<f',data,len(data)-12,float('nan'));source.write_bytes(data)
    assert measure(source)['nonfinite_positions']==1


@pytest.mark.parametrize('kind', ['duplicate_json','duplicate_bin','unknown'])
def test_numeric_preflight_refuses_ambiguous_or_unknown_glb_chunks(tmp_path,kind):
    import struct
    measure,source=encoded_fixture(tmp_path)
    data=bytearray(source.read_bytes());jsonlen=struct.unpack_from('<I',data,12)[0]
    extra=data[12:20+jsonlen] if kind=='duplicate_json' else data[20+jsonlen:] if kind=='duplicate_bin' else struct.pack('<II',4,123)+b'abcd'
    data+=extra;struct.pack_into('<I',data,8,len(data));source.write_bytes(data)
    with pytest.raises(ValueError):measure(source)


def test_numeric_preflight_refuses_meshopt_even_for_integer_attributes(tmp_path):
    accessor={'bufferView':0,'componentType':5123,'count':1,'type':'VEC3'}
    view={'buffer':0,'byteLength':12,'extensions':{'EXT_meshopt_compression':{}}}
    measure,source=encoded_fixture(tmp_path,{'accessors':[accessor],'bufferViews':[view]})
    with pytest.raises(ValueError,match='compressed'):measure(source)
