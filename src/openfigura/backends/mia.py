"""Optional external Make-It-Animatable runtime; core remains stdlib-only."""
import json
import os
from pathlib import Path
from openfigura.backends import base
from openfigura.core import registry
from openfigura.core.registry import Capabilities

CHECKPOINTS=('joints_coarse','joints','bw')

class MiaBackend:
    id='mia'
    kind='postprocess'

    def paths(self):
        root=Path(os.environ.get('OPENFIGURA_MIA_HOME',str(Path.home()/'Desktop/Local/Opensource/Make-It-Animatable')))
        override=os.environ.get('OPENFIGURA_MIA_PYTHON')
        candidates=[root/'.venv-mac/bin/python',root/'.venv/bin/python',root/'.venv/Scripts/python.exe']
        python=Path(override) if override else next((p for p in candidates if p.is_file()),candidates[0])
        return root,python

    def capabilities(self):
        root,python=self.paths()
        if not (root/'model.py').is_file() or not python.is_file():
            return Capabilities(False,reason='Make-It-Animatable source/runtime missing; set OPENFIGURA_MIA_HOME and OPENFIGURA_MIA_PYTHON')
        missing=[n for n in CHECKPOINTS if not (root/f'output/best/new/{n}.pth').is_file()]
        if missing:return Capabilities(False,reason='MIA checkpoint missing: '+','.join(missing))
        if not (root/'data/Mixamo/bones.fbx').is_file():
            return Capabilities(False,reason='MIA external Mixamo skeleton template missing')
        probe=base.run([str(python),'-c',"import torch,torch_cluster,bpy,trimesh,shapely; from pytorch3d.transforms import Transform3d; print('MIA_READY',torch.__version__,'CUDA',torch.cuda.is_available())"],timeout_s=60)
        ready=probe.ok and 'MIA_READY' in probe.stdout_tail
        return Capabilities(ready,hardware='cuda' if ready and 'CUDA True' in probe.stdout_tail else 'cpu',reason='' if ready else probe.stderr_tail or probe.stdout_tail,
            notes={'framework':'Make-It-Animatable','coordinates':'neural prediction','cuda':'explicit device, depends on external runtime','mps':'unverified','status':'experimental; requires fit and visual checks','motion':'rigging only; not motion synthesis'})

    def autorig(self,model,output,**options):
        from openfigura.backends.blender import BlenderBackend
        root,python=self.paths();binary=BlenderBackend().binary()
        if not binary:return {'produced':False,'stderr_tail':'Blender not found','exit_code':1}
        native=output.parent/'autorig-native';native.mkdir(exist_ok=False)
        cfg=output.with_suffix('.autorig-config.json')
        cfg.write_text(json.dumps({'repo':str(root.resolve()),'model':str(model.resolve()),
                                  'native':str(native.resolve()),'output':str(output.resolve()),**options}))
        worker=Path(__file__).with_name('mia_worker.py')
        result=base.run([str(python),str(worker),'--',str(cfg.resolve())],timeout_s=7200)
        output.with_suffix('.neural-stdout.log').write_text(result.stdout_tail)
        output.with_suffix('.neural-stderr.log').write_text(result.stderr_tail)
        report=native/'inference-report.json'
        fit=native/'fit-report.json'
        fit_evidence={'fit_validation':json.loads(fit.read_text())} if fit.is_file() else {}
        if not result.ok or not report.is_file() or 'INFERENCE_DONE' not in result.stdout_tail:
            return {**result.ledger(),**fit_evidence,'produced':False}
        metadata=json.loads(report.read_text())
        bind=base.run([binary,'-b','--factory-startup','--python-exit-code','1','--python',
            str(Path(__file__).with_name('neural_bind_worker.py')),'--',str(cfg.resolve())],timeout_s=600)
        output.with_suffix('.bind-stdout.log').write_text(bind.stdout_tail)
        output.with_suffix('.bind-stderr.log').write_text(bind.stderr_tail)
        binding=output.with_suffix('.bind-report.json')
        produced=bind.ok and output.is_file() and binding.is_file() and 'NEURAL_BIND_DONE' in bind.stdout_tail
        return {**metadata,'inference':result.ledger(),**bind.ledger(),'produced':produced,
                'binding':json.loads(binding.read_text()) if produced else {},
                'contact_validation':{'status':'unavailable','reason':'static rig only; animation requires separate contact evaluation'}}

registry.register('mia',MiaBackend,'external neural humanoid skeleton/skin prediction; no manual coordinates')
