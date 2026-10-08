"""Optional Godot retargeting plus Blender IK/contact correction."""
import json,os,shutil
from pathlib import Path
from openfigura.backends import base
from openfigura.core import registry
from openfigura.core.registry import Capabilities

class NativeMotionBackend:
    id='native-motion';kind='postprocess'
    def binary(self):return os.environ.get('OPENFIGURA_GODOT_BIN') or base.which('godot')
    def capabilities(self):
        from openfigura.backends.blender import BlenderBackend
        binary=self.binary()
        if not binary or not BlenderBackend().binary():return Capabilities(False,reason='Godot and Blender required')
        probe=base.run([binary,'--headless','--version'],timeout_s=20)
        # RetargetModifier3D was introduced in 4.4; the current worker is tested in 4.7.
        version=probe.stdout_tail.strip().split('.')
        valid=probe.ok and len(version)>1 and version[0]=='4' and version[1].isdigit() and int(version[1])>=4
        return Capabilities(valid,hardware='cpu',reason='' if valid else 'Godot 4.4+ with RetargetModifier3D required',
            notes={'tested':'Godot4.7.2/Blender5.2.2','bones':'matching names; Mixamo hands required',
                   'contact':'mandatory region checks after native two-bone IK; not full cloth physics'})
    def retarget(self,model,animation,output,frames,fps):
        from openfigura.backends.blender import BlenderBackend
        native=output.parent/'motion-native';native.mkdir(exist_ok=False)
        shutil.copy2(model,native/'target.glb');shutil.copy2(animation,native/'reference.glb')
        (native/'project.godot').write_text('config_version=5\n[application]\nconfig/name="OpenFigura motion worker"\nrun/main_scene="res://main.tscn"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n')
        (native/'main.tscn').write_text('[gd_scene load_steps=2 format=3]\n[ext_resource type="Script" path="res://main.gd" id="1"]\n[node name="Worker" type="Node3D"]\nscript=ExtResource("1")\n')
        shutil.copy2(Path(__file__).with_name('retarget_worker.gd'),native/'main.gd')
        cfg=output.with_suffix('.motion-config.json');cfg.write_text(json.dumps({'model':str(model.resolve()),
            'native':str(native.resolve()),'output':str(output.resolve()),'frames':frames,'fps':fps}))
        imports=base.run([self.binary(),'--headless','--path',str(native),'--editor','--import'],timeout_s=180)
        (native/'import.log').write_text(imports.stdout_tail+imports.stderr_tail)
        if not imports.ok:return {**imports.ledger(),'produced':False}
        poses=base.run([self.binary(),'--headless','--path',str(native),'--fixed-fps',str(fps),
            '--quit-after',str(frames+10),'--',str(cfg.resolve())],timeout_s=180)
        (native/'retarget.log').write_text(poses.stdout_tail+poses.stderr_tail)
        if not poses.ok or not (native/'poses.json').exists():return {**poses.ledger(),'produced':False}
        binding=base.run([BlenderBackend().binary(),'-b','--factory-startup','--python-exit-code','1','--python',
            str(Path(__file__).with_name('motion_worker.py')),'--',str(cfg.resolve())],timeout_s=600)
        (native/'bake.log').write_text(binding.stdout_tail+binding.stderr_tail)
        report=native/'contact-report.json';contact=json.loads(report.read_text()) if report.exists() else {'status':'unavailable'}
        return {**binding.ledger(),'retarget':poses.ledger(),'produced':binding.ok and output.is_file() and 'MOTION_DONE' in binding.stdout_tail,
            'contact_validation':contact,'manual_coordinates':False,'manual_keyframes':False,
            'frameworks':['Godot RetargetModifier3D','Blender native IK'],'limitations':['matching-name humanoids only','integer-frame regional contact checks','no cloth dynamics or ground-contact guarantee']}
registry.register('native-motion',NativeMotionBackend,'native humanoid retargeting and IK/contact validation')
