"""Small independent continuity gate; does not certify anatomical placement."""
import math

CHAINS=[('mixamorig:'+side+parent,'mixamorig:'+side+child)
        for side in ('Left','Right') for parent,child in
        [('Arm','ForeArm'),('ForeArm','Hand'),('UpLeg','Leg')]]

def audit(skeleton, extent, max_gap_ratio=.03):
    report={'status':'pass','max_gap_ratio':max_gap_ratio,'joints':[],
            'scope':'elbow/wrist/knee continuity only; not full anatomical or skin validation'}
    if not math.isfinite(extent) or extent<=0:
        return {**report,'status':'fail','error':'invalid model extent'}
    names=skeleton.get('names',[]);heads=skeleton.get('heads',[]);tails=skeleton.get('tails',[])
    if not names or len(names)!=len(heads) or len(names)!=len(tails):
        return {**report,'status':'fail','error':'missing/inconsistent skeleton'}
    index={name:i for i,name in enumerate(names)}
    for parent,child in CHAINS:
        if parent not in index or child not in index:continue
        a=tails[index[parent]];b=heads[index[child]]
        if len(a)!=3 or len(b)!=3 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in a+b):
            return {**report,'status':'fail','error':'nonfinite joint coordinates'}
        gap=math.dist(a,b);ratio=gap/extent
        report['joints'].append({'parent':parent,'child':child,'gap':gap,'gap_ratio':ratio})
        if ratio>max_gap_ratio:report['status']='fail'
    if not report['joints']:report.update(status='fail',error='no recognized humanoid continuity checks')
    return report
