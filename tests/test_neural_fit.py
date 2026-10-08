from openfigura.backends import neural_fit

def test_detached_wrist_is_rejected():
    skeleton={'names':['mixamorig:LeftForeArm','mixamorig:LeftHand'],
        'heads':[[0,0,0],[0,.25,0]],'tails':[[0,.1,0],[0,.3,0]]}
    report=neural_fit.audit(skeleton,1)
    assert report['status']=='fail' and report['joints'][0]['gap_ratio']==.15

def test_connected_wrist_passes():
    skeleton={'names':['mixamorig:LeftForeArm','mixamorig:LeftHand'],
        'heads':[[0,0,0],[0,.1001,0]],'tails':[[0,.1,0],[0,.2,0]]}
    assert neural_fit.audit(skeleton,1)['status']=='pass'

def test_incomplete_humanoid_is_not_accepted():
    assert neural_fit.audit({'names':[],'heads':[],'tails':[]},1)['status']=='fail'
