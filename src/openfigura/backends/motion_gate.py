"""Backend-independent contact-gate runner for animated GLBs (isolated Blender)."""
from __future__ import annotations
import json
from pathlib import Path
from openfigura.backends import base
from openfigura.core import registry
from openfigura.core.registry import Capabilities


class MotionGateBackend:
    id = 'blender-motion-gate'
    kind = 'postprocess'

    def binary(self):
        from openfigura.backends.blender import BlenderBackend
        return BlenderBackend().binary()

    def capabilities(self) -> Capabilities:
        binary = self.binary()
        return Capabilities(bool(binary), reason='' if binary else 'blender not found',
                            hardware='cpu',
                            notes={'method': 'dominant-weight regional triangle BVH, integer frames',
                                   'verdict': 'pass only when require_clear accepts every checked frame',
                                   'limits': 'same as retarget gate: transition triangles excluded, no closed-volume proof, not cloth physics'})

    def gate(self, model: Path, report_path: Path, regions: dict | None = None,
             margin: float = 0.002) -> dict:
        model, report_path = Path(model).resolve(), Path(report_path).resolve()
        if not model.is_file():
            raise FileNotFoundError(model)
        if report_path.exists():
            raise FileExistsError('refusing to overwrite existing gate report')
        binary = self.binary()
        if not binary:
            raise RuntimeError('blender unavailable')
        report_path.parent.mkdir(parents=True, exist_ok=True)
        config = report_path.with_suffix('.gate-config.json')
        payload = {'model': str(model), 'report': str(report_path), 'margin': margin}
        if regions is not None:
            payload['regions'] = dict(regions)
        config.write_text(json.dumps(payload), encoding='utf-8')
        result = base.run([binary, '-b', '--factory-startup', '--python-exit-code', '1',
                           '--python', str(Path(__file__).with_name('motion_gate_worker.py')),
                           '--', str(config)], timeout_s=3600)
        config.unlink()
        report = None
        if report_path.is_file():
            try:
                report = json.loads(report_path.read_text(encoding='utf-8'))
            except (ValueError, OSError) as exc:
                result = base.CommandResult(result.argv, result.exit_code or 1,
                                            result.wall_seconds, result.stdout_tail,
                                            result.stderr_tail + f'\nInvalid gate report: {exc}')
        if result.exit_code == 0 and report is None:
            result = base.CommandResult(result.argv, 1, result.wall_seconds,
                                        result.stdout_tail,
                                        result.stderr_tail + '\nBlender produced no gate report')
        if report is not None and report.get('status') == 'pass' and result.exit_code != 0:
            result = base.CommandResult(result.argv, result.exit_code, result.wall_seconds,
                                        result.stdout_tail,
                                        result.stderr_tail + '\nGate verdict contradicts exit code')
            report['status'] = 'fail'
            report['error'] = 'worker exited nonzero despite pass verdict'
        return {'backend': self.id, **result.ledger(), 'stdout_tail': result.stdout_tail,
                'report_path': str(report_path), 'report': report}


registry.register('blender-motion-gate', MotionGateBackend,
                  'standalone regional contact gate for any animated skinned GLB')
