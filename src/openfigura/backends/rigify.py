"""External Blender Rigify adapter; calibrated/experimental, not neural autorigging."""
from pathlib import Path
import json
from openfigura.backends import base
from openfigura.core import registry
from openfigura.core.registry import Capabilities

class RigifyBackend:
    id='rigify'
    kind='postprocess'

    def capabilities(self):
        from openfigura.backends.blender import BlenderBackend
        binary=BlenderBackend().binary()
        if binary is None:
            return Capabilities(False,reason='Blender not found')
        probe=base.run([binary,'-b','--factory-startup','--python-exit-code','1',
            '--python-expr',"import addon_utils; addon_utils.enable('rigify',default_set=True); import bpy; assert 'rigify' in bpy.context.preferences.addons; print('OPENFIGURA_RIGIFY_READY')"],timeout_s=30)
        ok=probe.ok and 'OPENFIGURA_RIGIFY_READY' in probe.stdout_tail
        return Capabilities(ok,hardware='cpu',reason='' if ok else probe.stderr_tail or 'Rigify probe failed',
            notes={'calibration':'required','status':'experimental basic human, no fingers','skin_methods':'automatic|capsule'})

    def rig(self,model: Path,calibration: Path,output: Path,skin_method: str):
        from openfigura.backends.blender import BlenderBackend
        binary=BlenderBackend().binary()
        cfg=output.with_suffix('.rig-config.json')
        cfg.write_text(json.dumps({'model':str(model.resolve()),'calibration':str(calibration.resolve()),
                                  'output':str(output.resolve()),'skin_method':skin_method}))
        command=[binary,'-b','--factory-startup','--python-exit-code','1','--python',
                 str(Path(__file__).with_name('rigify_worker.py')),'--',str(cfg.resolve())]
        result=base.run(command,timeout_s=600)
        output.with_suffix('.rig-stdout.log').write_text(result.stdout_tail)
        output.with_suffix('.rig-stderr.log').write_text(result.stderr_tail)
        report=output.with_suffix('.rig-report.json')
        produced=result.ok and output.is_file() and report.is_file() and 'OPENFIGURA_RIG_DONE' in result.stdout_tail
        contact_report=output.with_suffix('.contact-report.json')
        contact_evidence={'contact_validation':json.loads(contact_report.read_text())} if contact_report.is_file() else {}
        return {**(json.loads(report.read_text()) if produced else {}),**contact_evidence,**result.ledger(),
                'produced':produced,'skin_method':skin_method}

registry.register('rigify',RigifyBackend,'experimental calibrated basic-human Rigify binding, no silent fallback')
