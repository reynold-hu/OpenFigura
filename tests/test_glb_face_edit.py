import json, struct, hashlib
from copy import deepcopy
from pathlib import Path
import pytest
from openfigura.core.glb_faces import prune_faces

def fixture(path):
    blob=struct.pack('<12f',0,0,0,1,0,0,0,1,0,0,0,1)+struct.pack('<12I',0,1,2,0,3,1,1,3,2,2,3,0)
    doc={'asset':{'version':'2.0'},'buffers':[{'byteLength':len(blob)}],
         'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':48},{'buffer':0,'byteOffset':48,'byteLength':48}],
         'accessors':[{'bufferView':0,'componentType':5126,'count':4,'type':'VEC3'},
                      {'bufferView':1,'componentType':5125,'count':12,'type':'SCALAR'}],
         'meshes':[{'primitives':[{'attributes':{'POSITION':0,'NORMAL':0,'TEXCOORD_0':0},'indices':1,'material':0}]}],
         'materials':[{'pbrMetallicRoughness':{'baseColorFactor':[1,0,0,1]}}]}
    raw=json.dumps(doc).encode();raw+=b' '*((-len(raw))%4)
    path.write_bytes(struct.pack('<III',0x46546c67,2,28+len(raw)+len(blob))+struct.pack('<II',len(raw),0x4e4f534a)+raw+struct.pack('<II',len(blob),0x004e4942)+blob)
    return doc,blob

def read(path):
    data=path.read_bytes();n=struct.unpack_from('<I',data,12)[0]
    return json.loads(data[20:20+n]),data[28+n:]

def write(path,doc,blob):
    raw=json.dumps(doc).encode();raw+=b' '*((-len(raw))%4)
    path.write_bytes(struct.pack('<III',0x46546c67,2,28+len(raw)+len(blob))+struct.pack('<II',len(raw),0x4e4f534a)+raw+struct.pack('<II',len(blob),0x004e4942)+blob)

def test_face_prune_preserves_original_attributes_bytes_and_materials(tmp_path):
    source=tmp_path/'s.glb';out=tmp_path/'out.glb';doc,blob=fixture(source); original=source.read_bytes()
    report=prune_faces(source,out,{(0,0):[0,2,3]},max_removed_fraction=.3)
    new,newblob=read(out)
    assert source.read_bytes()==original
    assert newblob[:len(blob)]==blob
    assert new['materials']==doc['materials']
    assert new['meshes'][0]['primitives'][0]['attributes']==doc['meshes'][0]['primitives'][0]['attributes']
    assert new['accessors'][:2]==doc['accessors']
    assert struct.unpack('<9I',newblob[len(blob):])==(0,1,2,1,3,2,2,3,0)
    assert report['removed_faces']==1 and report['attribute_bytes_preserved'] is True
    assert report['repair_complete'] is False
    assert report['source_sha256']==hashlib.sha256(original).hexdigest()
    assert report['output_sha256']==hashlib.sha256(out.read_bytes()).hexdigest()
    assert new['bufferViews'][:2]==doc['bufferViews']

def test_other_primitive_and_scene_metadata_unchanged_and_budget_independent(tmp_path):
    source=tmp_path/'s.glb';doc,blob=fixture(source)
    doc['meshes'][0]['primitives'].append(deepcopy(doc['meshes'][0]['primitives'][0]))
    doc.update(nodes=[{'mesh':0,'extras':{'tag':'keep'}}],scenes=[{'nodes':[0]}],
               extras={'author':'test'},textures=[{'source':0}],images=[{'uri':'original.png'}])
    write(source,doc,blob);out=tmp_path/'out.glb'
    prune_faces(source,out,{(0,0):[0,1,2]},max_removed_fraction=.3)
    new,_=read(out)
    for field in ('nodes','scenes','extras','textures','images'):assert new[field]==doc[field]
    assert new['meshes'][0]['primitives'][1]==doc['meshes'][0]['primitives'][1]
    with pytest.raises(ValueError,match='budget'):
        prune_faces(source,tmp_path/'bad.glb',{(0,0):[0,1],(0,1):[0,1,2,3]},max_removed_fraction=.3)

@pytest.mark.parametrize('kind',['bounds','sparse','compression','negative_index'])
def test_invalid_index_accessor_has_no_output(tmp_path,kind):
    source=tmp_path/'s.glb';doc,blob=fixture(source);out=tmp_path/'out.glb'
    if kind=='bounds':doc['bufferViews'][1]['byteLength']=47
    elif kind=='sparse':doc['accessors'][1]['sparse']={'count':1}
    elif kind=='compression':doc['bufferViews'][1]['extensions']={'EXT_meshopt_compression':{}}
    else:doc['meshes'][0]['primitives'][0]['indices']=-1
    write(source,doc,blob)
    with pytest.raises(ValueError):prune_faces(source,out,{(0,0):[0,1,2,3]})
    assert not out.exists()

@pytest.mark.parametrize('mask', [[True],[0,0],[-1],[4],[],[1.2]])
def test_invalid_mask_has_no_output(tmp_path,mask):
    source=tmp_path/'s.glb';fixture(source);out=tmp_path/'out.glb'
    with pytest.raises(ValueError):prune_faces(source,out,{(0,0):mask},max_removed_fraction=.9)
    assert not out.exists()

def test_budget_alias_and_existing_output_refused(tmp_path):
    source=tmp_path/'s.glb';fixture(source);out=tmp_path/'out.glb'
    with pytest.raises(ValueError):prune_faces(source,out,{(0,0):[0,1,2]})
    assert not out.exists()
    with pytest.raises(ValueError):prune_faces(source,source,{(0,0):[0,1,2,3]})
    out.write_bytes(b'existing')
    with pytest.raises(FileExistsError):prune_faces(source,out,{(0,0):[0,1,2,3]})
    assert out.read_bytes()==b'existing'

def test_dangling_output_symlink_refused(tmp_path):
    source=tmp_path/'s.glb';fixture(source)
    out=tmp_path/'out.glb';target=tmp_path/'missing.glb';out.symlink_to(target)
    with pytest.raises(FileExistsError):prune_faces(source,out,{(0,0):[0,1,2,3]})
    assert out.is_symlink() and not target.exists()

def test_publication_race_preserves_existing_entry_and_cleans_temp(tmp_path,monkeypatch):
    from openfigura.core import glb_faces
    source=tmp_path/'s.glb';fixture(source);out=tmp_path/'out.glb';real=glb_faces.os.link
    def race(temp,dest):
        Path(dest).write_bytes(b'other writer')
        return real(temp,dest)
    monkeypatch.setattr(glb_faces.os,'link',race)
    with pytest.raises(FileExistsError):prune_faces(source,out,{(0,0):[0,1,2,3]})
    assert out.read_bytes()==b'other writer'
    assert {p.name for p in tmp_path.iterdir()}=={'s.glb','out.glb'}
