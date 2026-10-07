from types import SimpleNamespace
from openfigura.backends import blender

def test_camera_bounds_exclude_imported_bone_widgets():
    character=SimpleNamespace(type='MESH',hide_render=False,name='Character')
    widget=SimpleNamespace(type='MESH',hide_render=True,name='Icosphere')
    rig=SimpleNamespace(type='ARMATURE',hide_render=False,name='Rig')
    assert blender.renderable_meshes([widget,character,rig])==[character]

def test_importer_widget_in_hidden_collection_is_excluded():
    character=SimpleNamespace(type='MESH',hide_render=False,visible_get=lambda:True)
    widget=SimpleNamespace(type='MESH',hide_render=False,visible_get=lambda:False)
    assert blender.renderable_meshes([character,widget])==[character]
