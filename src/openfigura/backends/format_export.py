"""Optional Blender-driven multi-format export (FBX/OBJ/STL/USD).

The verified GLB stays the source of truth: conversion always starts from
an inspected snapshot, and every format that loses data (skin, animation,
textures) says so in its report. GLB export itself remains stdlib-only.
"""
from __future__ import annotations
import json
import subprocess
import tempfile
import time
from pathlib import Path
from openfigura.backends import base
from openfigura.core import registry
from openfigura.core.registry import Capabilities

PROBE = ('import bpy,addon_utils,json\n'
         'ok={}\n'
         'for ext,mods in [("io_scene_fbx",[("export_scene","fbx")]),'
         '("io_mesh_stl",[("wm","stl_export")]),(None,[("wm","obj_export"),("wm","usd_export")])]:\n'
         ' if ext:\n'
         '  try: addon_utils.enable(ext,default_set=False)\n'
         '  except Exception: pass\n'
         ' for m,n in mods: ok[n]=hasattr(getattr(bpy.ops,m),n)\n'
         'print("FORMATS"+json.dumps(ok))\n')


class FormatExportBackend:
    id = 'blender-formats'
    kind = 'postprocess'
    EXTENSIONS = {'fbx': 'fbx', 'obj': 'obj', 'stl': 'stl', 'usd': 'usd'}

    def binary(self):
        from openfigura.backends.blender import BlenderBackend
        return BlenderBackend().binary()

    def _probe(self):
        binary = self.binary()
        if not binary:
            return {}
        folder = tempfile.mkdtemp(prefix='openfigura-fmt-probe-')
        script = Path(folder) / 'probe.py'
        script.write_text(PROBE, encoding='utf-8')
        result = base.run([binary, '-b', '--factory-startup', '--python', str(script)], timeout_s=120)
        script.unlink()
        for line in (result.stdout_tail or '').splitlines():
            if line.startswith('FORMATS'):
                try:
                    return {k: bool(v) for k, v in json.loads(line[7:]).items()}
                except ValueError:
                    return {}
        return {}

    def capabilities(self) -> Capabilities:
        binary = self.binary()
        if not binary:
            return Capabilities(False, reason='blender not found',
                                notes={'glb': 'always available via stdlib export'})
        found = self._probe()
        formats = sorted(name for name, key in
                         {'fbx': 'fbx', 'obj': 'obj', 'stl': 'stl', 'usd': 'usd_export'}.items()
                         if found.get(key))
        return Capabilities(bool(formats), hardware='cpu',
                            reason='' if formats else 'no export operators enabled in this Blender',
                            notes={'formats': ','.join(['glb'] + formats), 'binary': binary,
                                   'usdz': 'not exposed by this Blender build'})

    def convert(self, model: Path, output: Path, fmt: str) -> dict:
        model, output = Path(model).resolve(), Path(output).resolve()
        if fmt not in self.EXTENSIONS:
            raise ValueError(f"unsupported format {fmt!r}; known: {sorted(self.EXTENSIONS)}")
        if output.exists() or output.resolve() == model:
            raise ValueError('refusing to overwrite output or source')
        if not model.is_file():
            raise FileNotFoundError(model)
        binary = self.binary()
        if not binary:
            raise RuntimeError('blender unavailable')
        output.parent.mkdir(parents=True, exist_ok=True)
        report_path = output.with_name(output.stem + f'.{fmt}-report.json')
        if report_path.exists():
            raise ValueError('refusing to overwrite existing report')
        cfg = {'model': str(model), 'output': str(output), 'format': fmt,
               'report': str(report_path)}
        with tempfile.TemporaryDirectory(prefix='openfigura-fmt-') as folder:
            config = Path(folder) / 'config.json'
            config.write_text(json.dumps(cfg), encoding='utf-8')
            argv = [binary, '-b', '--factory-startup', '--python-exit-code', '1', '--python',
                    str(Path(__file__).with_name('format_export_worker.py')), '--', str(config)]
            started = time.monotonic()
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=1200)
            ledger = base.CommandResult(argv, proc.returncode,
                                         round(time.monotonic() - started, 2),
                                         (proc.stdout or '')[-4000:],
                                         (proc.stderr or '')[-4000:]).ledger()
        report = None
        if report_path.is_file():
            try:
                report = json.loads(report_path.read_text(encoding='utf-8'))
            except (ValueError, OSError) as exc:
                ledger['exit_code'] = ledger['exit_code'] or 1
                ledger['stderr_tail'] += f'\nInvalid format report: {exc}'
        if proc.returncode == 0 and (not output.is_file() or report is None):
            ledger['exit_code'] = ledger['exit_code'] or 1
            ledger['stderr_tail'] += '\nBlender did not produce output and report'
        return {'backend': self.id, 'format': fmt, **ledger,
                'output': str(output), 'report_path': str(report_path), 'report': report}


registry.register('blender-formats', FormatExportBackend,
                  'FBX/OBJ/STL/USD conversion from a verified GLB via isolated Blender')
