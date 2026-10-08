"""Headless upstream PCAE trial; no manually placed bones or fallback weights."""
import sys,json,time,gc,hashlib
from pathlib import Path
cfg=json.loads(Path(sys.argv[-1]).read_text());repo=Path(cfg['repo']);sys.path.insert(0,str(repo))
import numpy as np,torch,trimesh
from pytorch3d.transforms import Transform3d
from model import PCAE
from util.dataset_mixamo import JOINTS_NUM,KINEMATIC_TREE,BONES_IDX_DICT,get_hips_transform
from util.utils import fix_random,get_normalize_transform,sample_mesh
root=Path(cfg['native']);source=Path(cfg['model']);start=time.monotonic();torch.set_num_threads(4);fix_random(cfg['seed']);device=torch.device(cfg['device'])
if device.type=='cuda' and not torch.cuda.is_available():raise RuntimeError('requested CUDA is unavailable')
class Tee:
 def __init__(self,original,path):self.original=original;self.log=path.open('w',buffering=1)
 def write(self,text):self.original.write(text);self.log.write(text)
 def flush(self):self.original.flush();self.log.flush()
sys.stdout=Tee(sys.stdout,root/'worker-progress.log')

import runpy
runpy.run_path(str(Path(__file__).with_name('mesh_sampling.py')))['seed_sampling'](trimesh,cfg['seed'])
mesh=trimesh.load(source,force='mesh',process=False)
source_extent=float(np.ptp(np.asarray(mesh.vertices),axis=0).max())
points=sample_mesh(mesh,32768,get_normals=False).astype(np.float32)
initial_sample_sha256=hashlib.sha256(points.tobytes()).hexdigest()
pts=torch.from_numpy(points)[None]
norm=get_normalize_transform(pts,keep_ratio=True,recenter=True);pts=norm.transform_points(pts)
print('INPUT',len(mesh.vertices),len(mesh.faces),flush=True)
def load(name,**kwargs):
 t=time.monotonic();m=PCAE(N=32768,input_normal=False,deterministic=True,output_dim=JOINTS_NUM,**kwargs)
 m.load(str(repo/f'output/best/new/{name}.pth'));m.to(device).eval();print('MODEL_LOADED',name,round(time.monotonic()-t,2),flush=True);return m
with torch.inference_mode():
 coarse=load('joints_coarse',predict_bw=False,predict_joints=True,predict_joints_tail=True)
 t=time.monotonic();coarse_joints=coarse(pts.to(device)).joints.cpu();print('COARSE_DONE',round(time.monotonic()-t,2),flush=True)
 (root/'coarse-joints.json').write_text(json.dumps({'heads':norm.inverse().transform_points(coarse_joints[...,:3])[0].numpy().tolist(),'tails':norm.inverse().transform_points(coarse_joints[...,3:])[0].numpy().tolist(),'names':list(BONES_IDX_DICT)}))
 del coarse;gc.collect()
 hips=coarse_joints[:,BONES_IDX_DICT['mixamorig:Hips'],:3]
 ru=coarse_joints[:,BONES_IDX_DICT['mixamorig:RightUpLeg'],:3];lu=coarse_joints[:,BONES_IDX_DICT['mixamorig:LeftUpLeg'],:3]
 rotate=Transform3d(matrix=get_hips_transform(hips,ru,lu).transpose(-1,-2));transform=norm.compose(rotate)
 mesh.vertices=transform.transform_points(torch.from_numpy(np.asarray(mesh.vertices,dtype=np.float32))[None])[0].numpy()
 hands=rotate.transform_points(coarse_joints[...,3:])[0].numpy()[[BONES_IDX_DICT['mixamorig:LeftHand'],BONES_IDX_DICT['mixamorig:RightHand']]]
 sampled=sample_mesh(mesh,32768,get_normals=False,attn_ratio=.5,attn_centers=hands,attn_geo_ratio=0).astype(np.float32)
 pts=torch.from_numpy(sampled)[None];norm2=get_normalize_transform(pts,keep_ratio=True,recenter=False)
 pts=norm2.transform_points(pts);vertices=norm2.transform_points(torch.from_numpy(np.asarray(mesh.vertices,dtype=np.float32))[None]);transform=transform.compose(norm2)
 model=load('joints',hierarchical_ratio=.5,kinematic_tree=KINEMATIC_TREE,predict_bw=False,predict_joints=True,predict_joints_tail=True,joints_attn_causal=True)
 t=time.monotonic();j=model(pts.to(device)).joints.cpu();print('JOINTS_DONE',round(time.monotonic()-t,2),flush=True)
 inverse=transform.inverse();heads=inverse.transform_points(j[...,:3])[0].numpy();tails=inverse.transform_points(j[...,3:])[0].numpy()
 np.savez(root/'skeleton.npz',heads=heads,tails=tails,names=np.array(list(BONES_IDX_DICT)),parents=np.array(KINEMATIC_TREE.parent_indices),transform=transform.get_matrix().numpy())
 del model;gc.collect()
 skeleton={'heads':heads.tolist(),'tails':tails.tolist(),'names':list(BONES_IDX_DICT),'parents':KINEMATIC_TREE.parent_indices}
 (root/'skeleton.json').write_text(json.dumps(skeleton))
 import runpy
 fit_validation=runpy.run_path(str(Path(__file__).with_name('neural_fit.py')))['audit'](skeleton,source_extent)
 (root/'fit-report.json').write_text(json.dumps(fit_validation,indent=2))
 if fit_validation['status']!='pass':raise ValueError('predicted elbow/wrist/knee continuity failed; see fit-report.json')
 model=load('bw',hierarchical_ratio=.5)
 t=time.monotonic();encoded=model.encode(pts.to(device));print('WEIGHT_ENCODE_DONE',round(time.monotonic()-t,2),flush=True)
 n=vertices.shape[1];weights=np.lib.format.open_memmap(root/'weights.npy',mode='w+',dtype=np.float32,shape=(n,JOINTS_NUM))
 chunk=cfg['query_chunk']
 for offset in range(0,n,chunk):
  t=time.monotonic();logits=model.decode(encoded,vertices[:,offset:offset+chunk].to(device));bw=model.actvn(model.bw_head(logits))
  if not isinstance(model.actvn,torch.nn.Softmax):bw=bw/(bw.sum(-1,keepdim=True)+1e-10)
  weights[offset:offset+chunk]=bw[0].cpu().numpy();weights.flush()
  print('WEIGHTS',min(offset+chunk,n),'/',n,round(time.monotonic()-t,2),flush=True)
 del model;gc.collect()
 if not np.isfinite(weights).all() or not np.isfinite(heads).all() or not np.isfinite(tails).all():raise ValueError('nonfinite neural output')
 if np.min(weights)<0 or not np.allclose(weights.sum(1),1,atol=1e-4):raise ValueError('invalid neural weights')
 np.save(root/'vertices.npy',trimesh.load(source,force='mesh',process=False).vertices.astype(np.float32))
 report={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'device':str(device),'torch':torch.__version__,'threads':4,'seed':cfg['seed'],'surface_points':32768,'query_chunk':chunk,'vertices':n,'bones':JOINTS_NUM,'wall_seconds':round(time.monotonic()-start,2),'manual_coordinates':False,'skin_method':'upstream PCAE neural prediction','adaptations':['CPU dependencies compiled','headless without Gradio','cached upstream encoder across query chunks','no normals weight model or rest-pose model'],'visual_approval':'pending','rest_pose_inference':False,'trimesh':trimesh.__version__,'surface_sampling':'explicit seeded Generator stream'}

 (root/'skeleton.json').write_text(json.dumps({'heads':heads.tolist(),'tails':tails.tolist(),'names':list(BONES_IDX_DICT),'parents':KINEMATIC_TREE.parent_indices}))
 report['initial_sample_sha256']=initial_sample_sha256
 report['fit_validation']=fit_validation
 report['checkpoint_sha256']={n:hashlib.sha256((repo/f'output/best/new/{n}.pth').read_bytes()).hexdigest() for n in ('joints_coarse','joints','bw')}
 (root/'inference-report.json').write_text(json.dumps(report,indent=2));print('INFERENCE_DONE',json.dumps(report),flush=True)
