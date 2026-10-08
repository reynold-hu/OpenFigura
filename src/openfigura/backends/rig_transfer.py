"""Optional Blender-rigged skin/skeleton transfer between two GLBs of one
character. Original implementation; refuses non-overlap instead of guessing."""
from __future__ import annotations
import json
import math
import tempfile
import subprocess
import time
from pathlib import Path
from openfigura.backends import base
from openfigura.core import registry
from openfigura.core.registry import Capabilities


class RigTransferBackend:
    id = 'blender-rig-transfer'
    kind = 'postprocess'

    def binary(self):
        from openfigura.backends.blender import BlenderBackend
        return BlenderBackend().binary()

    def capabilities(self) -> Capabilities:
        binary = self.binary()
        return Capabilities(bool(binary), reason='' if binary else 'blender not found',
                            hardware='cpu',
                            notes={'method': 'rest-pose nearest-triangle barycentric weight blend, top-N influences',
                                   'requires': 'rigged source GLB + static unrigged target GLB in matching rest pose',
                                   'limits': 'no semantic correspondence, no deformation validation; posed review required'})

    def transfer(self, target: Path, source: Path, output: Path, params: dict | None = None) -> dict:
        target, source = Path(target).resolve(), Path(source).resolve()
        output = Path(output).resolve()
        if target == source:
            raise ValueError('target and source must be different files')
        if not target.is_file() or not source.is_file():
            raise ValueError('target and source must exist')
        if output.exists() or output == target or output == source:
            raise ValueError('refusing to overwrite source or existing output')
        params = dict(params or {})
        limit = params.get('max_influences', 4)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 8:
            raise ValueError('max_influences must be an integer in 1..8')
        ratio = params.get('refuse_distance_ratio', 0.05)
        if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not math.isfinite(ratio) or not 0 < ratio <= 0.5:
            raise ValueError('refuse_distance_ratio must be finite in (0, 0.5]')
        binary = self.binary()
        if not binary:
            raise RuntimeError('blender unavailable')
        output.parent.mkdir(parents=True, exist_ok=True)
        report_path = output.with_suffix('.rig-transfer-report.json')
        if report_path.exists():
            raise ValueError('refusing to overwrite existing report')
        cfg = {'target': str(target), 'source': str(source), 'output': str(output),
               'params': params, 'report': str(report_path)}
        with tempfile.TemporaryDirectory(prefix='openfigura-rigx-') as folder:
            config = Path(folder) / 'config.json'
            config.write_text(json.dumps(cfg), encoding='utf-8')
            argv = [binary, '-b', '--factory-startup', '--python-exit-code', '1', '--python',
                    str(Path(__file__).with_name('rig_transfer_worker.py')), '--', str(config)]
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
                ledger['stderr_tail'] += f'\nInvalid transfer report: {exc}'
        if proc.returncode == 0 and (not output.is_file() or report is None):
            ledger['exit_code'] = ledger['exit_code'] or 1
            ledger['stderr_tail'] += '\nBlender did not produce output and report'
        return {'backend': self.id, **ledger, 'output': str(output),
                'report_path': str(report_path), 'report': report}


registry.register('blender-rig-transfer', RigTransferBackend,
                  'skeleton+skin transfer from rigged GLB to a matching static GLB')
