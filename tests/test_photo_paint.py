"""Real numeric projection checks; skipped on the intentionally bare core install."""
import importlib.util
import pytest
pytestmark=pytest.mark.skipif(importlib.util.find_spec('numpy') is None or importlib.util.find_spec('PIL') is None,reason='optional detail extra')

def test_reference_project_and_occlusion_weights():
    import numpy as np
    from openfigura._vendor.photo_paint import View,project,view_weights,Settings
    image=np.full((32,32,4),255,dtype='uint8');image[[0,-1],:,3]=0
    c2w=np.eye(4);c2w[:3,3]=[0,0,3];view=View(image,c2w,.5)
    vertices=np.array([[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0]],dtype=float)
    faces=np.array([[0,1,2],[0,2,3]])
    x,y,z=project(np.array([[0,0,0.]]),view);assert x[0]==16 and y[0]==16 and z[0]==3
    weights,_=view_weights(np.array([[0,0,0],[0,0,-1]],float),np.array([[0,0,1],[0,0,1]],float),view,vertices,faces,Settings(match_colour=False))
    assert weights[0]>.99 and weights[1]==0

def test_texture_projection_preserves_unobserved_colours():
    import numpy as np
    from openfigura._vendor.photo_paint import View,paint_texture,Settings
    texture=np.full((16,16,4),100,dtype='uint8');texture[:,:,3]=255
    vertices=np.array([[-.5,-.5,0],[.5,-.5,0],[.5,.5,0],[-.5,.5,0]],float)
    uv=np.array([[0,1],[1,1],[1,0],[0,0]],float);faces=np.array([[0,1,2],[0,2,3]])
    c2w=np.eye(4);c2w[:3,3]=[0,0,3]
    image=np.zeros((32,32,4),dtype='uint8');image[:,:,:3]=[250,20,10];image[:,:,3]=255;image[0,:,3]=0
    painted,weight=paint_texture(texture,vertices,uv,faces,[View(image,c2w,.5)],frame=((0,1,2),(1,1,1)),settings=Settings(match_colour=False))
    assert (weight>.9).any()
    assert np.array_equal(painted[weight==0],texture[weight==0])
    assert painted[weight>.9][:,0].mean()>230
