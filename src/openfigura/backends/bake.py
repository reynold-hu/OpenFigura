"""Local high-to-low tangent-normal and ambient-occlusion baking."""
from __future__ import annotations

import json
import math
from pathlib import Path
import subprocess
import tempfile
import time

from openfigura.backends import base
from openfigura.core.registry import Capabilities


class BakeBackend:
    id = 'blender-bake'
    kind = 'postprocess'

    def binary(self):
        from openfigura.backends.blender import BlenderBackend
        return BlenderBackend().binary()

    def capabilities(self):
        binary = self.binary()
        return Capabilities(bool(binary), reason='' if binary else 'blender not found',
            hardware='cpu', notes={'binary': binary, 'maps': ['normal', 'ao'],
            'limits': 'CPU Cycles; static GLBs with existing target UVs only; explicit world-unit rays; visual approval remains human.'})

    def bake(self, high: Path, low: Path, output: Path, params: dict) -> dict:
        high, low, output = (Path(p).resolve() for p in (high, low, output))
        if high == low or not high.is_file() or not low.is_file():
            raise ValueError('high and low must be distinct existing files')
        if output in (high, low) or output.exists():
            raise ValueError('refusing to overwrite source or existing output')
        if high.suffix.lower() != '.glb' or low.suffix.lower() != '.glb' or output.suffix.lower() != '.glb':
            raise ValueError('bake requires GLB inputs and output')
        settings = {'resolution': 512, 'samples': 16, 'maps': ['normal', 'ao'],
                    'cage_extrusion': .01, 'ray_distance': .1, **params}
        for key, lower, upper in [('resolution', 64, 4096), ('samples', 1, 128)]:
            value = settings[key]
            if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
                raise ValueError(f'{key} must be an integer in [{lower}, {upper}]')
        n = settings['resolution']
        if n & (n-1): raise ValueError('resolution must be a power of two')
        maps = settings['maps']
        if not isinstance(maps, list) or not maps or any(m not in ('normal', 'ao') for m in maps) or len(set(maps)) != len(maps):
            raise ValueError('maps must be a nonempty unique list of normal/ao')
        for key in ('cage_extrusion', 'ray_distance'):
            value = settings[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 10:
                raise ValueError(f'{key} must be finite world units in [0, 10]')
        report_path = output.with_suffix('.bake-report.json')
        blend = output.with_suffix('.blend')
        textures = {m: str(output.with_name(output.stem + '-' + m + '.png')) for m in maps}
        if any(Path(p).exists() for p in [report_path, blend, *textures.values()]):
            raise ValueError('refusing to overwrite bake artifacts')
        binary = self.binary()
        if not binary: raise RuntimeError('blender unavailable')
        output.parent.mkdir(parents=True, exist_ok=True)
        cfg = {'high': str(high), 'low': str(low), 'output': str(output), 'report': str(report_path),
               'blend': str(blend), 'textures': textures, 'params': settings}
        with tempfile.TemporaryDirectory(prefix='openfigura-bake-') as folder:
            config = Path(folder)/'config.json'; config.write_text(json.dumps(cfg), encoding='utf-8')
            argv = [binary, '-b', '--factory-startup', '--python-exit-code', '1', '--python',
                    str(Path(__file__).with_name('bake_worker.py')), '--', str(config)]
            start = time.monotonic()
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=3600)
            ledger = base.CommandResult(argv, proc.returncode, round(time.monotonic()-start, 2),
                       (proc.stdout or '')[-4000:], (proc.stderr or '')[-4000:]).ledger()
        report = None
        if report_path.is_file():
            try: report = json.loads(report_path.read_text(encoding='utf-8'))
            except (ValueError, OSError) as exc: ledger['stderr_tail'] += f'\nInvalid bake report: {exc}'
        produced = proc.returncode == 0 and isinstance(report, dict) and all(
            Path(p).is_file() for p in [output, blend, *textures.values()])
        if not produced and ledger['exit_code'] == 0:
            ledger['exit_code'] = 1
            ledger['stderr_tail'] += '\nBlender did not produce all bake artifacts and report'
        return {'backend': self.id, **ledger, 'produced': produced, 'output': str(output),
                'report_path': str(report_path), 'report': report, 'textures': textures, 'blend': str(blend)}
