"""Optional local static-mesh tools, run in an isolated Blender process."""
from __future__ import annotations

import json
import math
import subprocess
import tempfile
import time
from pathlib import Path

from openfigura.backends import base
from openfigura.backends.blender import BlenderBackend
from openfigura.core import registry
from openfigura.core.registry import Capabilities


class MeshToolsBackend:
    id = 'blender-mesh-tools'
    kind = 'mesh'

    def binary(self):
        return BlenderBackend().binary()

    def capabilities(self) -> Capabilities:
        binary = self.binary()
        return Capabilities(bool(binary), reason='' if binary else 'blender not found',
                            hardware='cpu', notes={'binary': binary, 'operations': ['segment', 'optimize', 'retopo', 'collision', 'uv'],
                            'limits': 'Static meshes only; segmentation is topology, not semantic parts. Retopology requires texture rebaking; bake unsupported.'})

    def process(self, model: Path, output: Path, operation: str, params: dict) -> dict:
        model, output = Path(model).resolve(), Path(output).resolve()
        if model == output or output.exists():
            raise ValueError('refusing to overwrite source or existing output')
        if not model.is_file():
            raise ValueError('source model does not exist')
        if operation not in {'segment', 'optimize', 'retopo', 'collision', 'uv'}:
            raise ValueError('unsupported mesh operation')
        params = dict(params)
        if operation == 'uv':
            params = {'mode': 'auto', 'resolution': 1024, 'margin_pixels': 2, **params}
            if params['mode'] not in {'auto', 'preserve', 'unwrap', 'repack'}:
                raise ValueError('uv mode must be auto, preserve, unwrap, or repack')
            resolution = params['resolution']
            if (isinstance(resolution, bool) or not isinstance(resolution, int)
                    or not 64 <= resolution <= 8192 or resolution & (resolution - 1)):
                raise ValueError('uv resolution must be a power of two in [64, 8192]')
            margin = params['margin_pixels']
            if (isinstance(margin, bool) or not isinstance(margin, (int, float))
                    or not math.isfinite(margin) or not 0 <= margin <= 32):
                raise ValueError('uv margin_pixels must be finite in [0, 32]')
        if operation == 'optimize':
            ratio = params.get('ratio')
            if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not math.isfinite(ratio) or not 0 < ratio <= 1:
                raise ValueError('ratio must be explicitly specified in (0, 1]')
        for key, default in ({'target_faces': None} if operation == 'retopo' else {'max_parts': 256} if operation == 'segment' else {}).items():
            value = params.get(key, default)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f'{key} must be a positive integer')
            params[key] = value
        if operation == 'retopo' and 'voxel_size' in params:
            value = params['voxel_size']
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                      or not math.isfinite(value) or not 0 < value <= 1):
                raise ValueError('voxel_size must be null or a finite number in (0, 1]')
        binary = self.binary()
        if not binary:
            raise RuntimeError('blender unavailable')
        output.parent.mkdir(parents=True, exist_ok=True)
        report_path = output.with_suffix('.mesh-report.json')
        if report_path.exists():
            raise ValueError('refusing to overwrite existing report')
        cfg = {'model': str(model), 'output': str(output), 'operation': operation, 'params': params, 'report': str(report_path)}
        with tempfile.TemporaryDirectory(prefix='openfigura-mesh-') as folder:
            config = Path(folder) / 'config.json'; config.write_text(json.dumps(cfg), encoding='utf-8')
            argv = [binary, '-b', '--factory-startup', '--python-exit-code', '1', '--python', str(Path(__file__).with_name('mesh_tools_worker.py')), '--', str(config)]
            started = time.monotonic()
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=3600)
            ledger = base.CommandResult(argv=argv, exit_code=proc.returncode, wall_seconds=round(time.monotonic()-started, 2), stdout_tail=(proc.stdout or '')[-4000:], stderr_tail=(proc.stderr or '')[-4000:]).ledger()
        report = None
        if report_path.is_file():
            try:
                report = json.loads(report_path.read_text(encoding='utf-8'))
            except (ValueError, OSError) as exc:
                ledger['exit_code'] = ledger['exit_code'] or 1
                ledger['stderr_tail'] += f'\nInvalid mesh report: {exc}'
        if proc.returncode == 0 and (not output.is_file() or report is None):
            ledger['exit_code'] = ledger['exit_code'] or 1
            ledger['stderr_tail'] += '\nBlender did not produce output and mesh report'
        return {'backend': self.id, **ledger, 'output': str(output), 'report_path': str(report_path), 'report': report}


registry.register('blender-mesh-tools', MeshToolsBackend,
                  'static mesh segment/optimize/retopo/collision/uv via isolated Blender')
