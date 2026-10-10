"""Backend: write ARKit-named morph targets onto a character via isolated Blender."""
from __future__ import annotations
import json
import subprocess
import tempfile
import time
from pathlib import Path
from openfigura.backends import base
from openfigura.core import registry
from openfigura.core.registry import Capabilities


class ExpressionsBackend:
    id = 'blender-expressions'
    kind = 'postprocess'

    def binary(self):
        from openfigura.backends.blender import BlenderBackend
        return BlenderBackend().binary()

    def capabilities(self) -> Capabilities:
        binary = self.binary()
        return Capabilities(bool(binary), reason='' if binary else 'blender not found',
                            hardware='cpu',
                            notes={'method': 'nearest-base morph fields with Gaussian falloff; one shape key per ARKit channel',
                                   'requires': 'CC0 faceunits pack + hm08 base mesh + expression alignment from expression_align',
                                   'limits': 'registration is face-anchored similarity only; no non-rigid fitting'})

    def run(self, model: Path, payload: Path, output: Path) -> dict:
        model, payload = Path(model).resolve(), Path(payload).resolve()
        output = Path(output).resolve()
        if not model.is_file() or not payload.is_file():
            raise ValueError('model and payload must exist')
        if output.exists() or output == model:
            raise ValueError('refusing to overwrite source or existing output')
        binary = self.binary()
        if not binary:
            raise RuntimeError('blender unavailable')
        output.parent.mkdir(parents=True, exist_ok=True)
        report_path = output.with_suffix('.expressions-report.json')
        if report_path.exists():
            raise ValueError('refusing to overwrite existing report')
        cfg = {'model': str(model), 'payload': str(payload), 'output': str(output),
               'report': str(report_path)}
        with tempfile.TemporaryDirectory(prefix='openfigura-expr-') as folder:
            config = Path(folder) / 'config.json'
            config.write_text(json.dumps(cfg), encoding='utf-8')
            argv = [binary, '-b', '--factory-startup', '--python-exit-code', '1', '--python',
                    str(Path(__file__).with_name('expressions_worker.py')), '--', str(config)]
            started = time.monotonic()
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=3600)
            ledger = base.CommandResult(argv, proc.returncode, round(time.monotonic() - started, 2),
                                        (proc.stdout or '')[-4000:], (proc.stderr or '')[-4000:]).ledger()
        report = None
        if report_path.is_file():
            try:
                report = json.loads(report_path.read_text(encoding='utf-8'))
            except (ValueError, OSError) as exc:
                ledger['exit_code'] = ledger['exit_code'] or 1
                ledger['stderr_tail'] += f'\nInvalid expressions report: {exc}'
        if proc.returncode == 0 and (not output.is_file() or report is None):
            ledger['exit_code'] = ledger['exit_code'] or 1
            ledger['stderr_tail'] += '\nBlender did not produce output and report'
        return {'backend': self.id, **ledger, 'output': str(output),
                'report_path': str(report_path), 'report': report}


registry.register('blender-expressions', ExpressionsBackend,
                  'ARKit morph targets written from CC0 face units + landmark registration')
