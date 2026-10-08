from pathlib import Path
import os

import pytest

from openfigura.backends.motion_gate import MotionGateBackend

blender = MotionGateBackend().binary()
pytestmark = pytest.mark.skipif(not blender, reason='requires a real Blender binary')

RUNS = Path(os.environ.get('OPENFIGURA_TEST_RUNS',
    str(Path.home() / 'Desktop/OpenFigura/.local/runs')))
BUNNY = RUNS / 'openfigura-neural-rig-trial-2026-10-07/tasks/bunny-motion-mcp/artifacts/model-animated.glb'

# A real, known-bad static bind pose: the scifi MIA autorig rests its hands on
# the thighs with sub-margin clearance (the same asset whose retarget the
# in-loop gate rejected 2026-10-08). No synthetic fixture needed.
SCIFI_REST = next(RUNS.glob(
    'openfigura-3d-loop-2026-10-08/tasks/mesh-chain/stages/*/artifacts/model-autorig.glb'), None)


def test_gate_passes_real_bunny_animation(tmp_path):
    if not BUNNY.is_file():
        pytest.skip('bunny evidence missing')
    report = tmp_path / 'gate.json'
    result = MotionGateBackend().gate(BUNNY, report)
    assert result['exit_code'] == 0, result['stderr_tail']
    data = result['report']
    assert data['status'] == 'pass', data
    assert data['regions']['source'] == 'auto-mixamorig'
    assert data['summary']['crossing_rows'] == 0
    assert data['frames'] >= 31


def test_gate_rejects_real_sub_margin_bind_pose(tmp_path):
    if SCIFI_REST is None or not SCIFI_REST.is_file():
        pytest.skip('scifi autorig evidence missing')
    report = tmp_path / 'gate.json'
    result = MotionGateBackend().gate(SCIFI_REST, report)
    assert result['exit_code'] == 0, result['stderr_tail']
    data = result['report']
    assert data['status'] == 'fail', data
    assert 'clearance' in data['error'] or 'intersection' in data['error']
    assert data['regions']['source'] == 'auto-mixamorig'
    assert result['report']['summary']['min_distance'] < data['margin']


def test_gate_refuses_overwrite_and_missing_input(tmp_path):
    with pytest.raises(FileNotFoundError):
        MotionGateBackend().gate(tmp_path / 'nope.glb', tmp_path / 'g.json')
