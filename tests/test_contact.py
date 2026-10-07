import pytest
from openfigura.backends import contact

def test_crossing_in_intermediate_frame_blocks_export():
    with pytest.raises(ValueError,match='frame 8'):
        contact.require_clear([{'frame':1,'pair':'hand/torso','crossings':0,'minimum_vertex_distance':.03},
            {'frame':8,'pair':'hand/torso','crossings':2083,'minimum_vertex_distance':0}],.002)

def test_margin_blocks_near_contact_even_without_crossing():
    with pytest.raises(ValueError,match='clearance'):
        contact.require_clear([{'frame':4,'pair':'hand/torso','crossings':0,'minimum_vertex_distance':.001}],.002)

def test_clear_regions_pass():
    contact.require_clear([{'frame':1,'pair':'hand/torso','crossings':0,'minimum_vertex_distance':.03}],.002)

def test_empty_region_cannot_pass():
    with pytest.raises(ValueError):
        contact.require_clear([{'frame':1,'pair':'hand/torso','crossings':0,'minimum_vertex_distance':None}],.002)

@pytest.mark.parametrize('config',[{}, {'pairs':[]}, {'pairs':[{'a':['hand'],'b':['torso']}],'margin':-1},
    {'pairs':[{'a':['hand'],'b':['hand']}],'margin':.002}])
def test_invalid_contact_config_is_rejected(config):
    with pytest.raises(ValueError):contact.validate_config(config)
