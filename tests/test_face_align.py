import json
from pathlib import Path

import pytest

from openfigura.core import engine, registry
from openfigura.core.task import Task, sha256_file
from openfigura.core.registry import Capabilities
from openfigura.backends.face_align import polygon_from_landmarks, FACE_OVAL
from test_engine import make_minimal_glb


def fake_landmarks():
    # A tiny 478-point ring so FACE_OVAL indices resolve.
    return [(0.3 + 0.1 * (i % 10) / 10, 0.3 + 0.1 * (i % 7) / 10, 0.0) for i in range(478)]


class FakeFace:
    id = 'mediapipe-face'
    def __init__(self, detection, available=True, reason=''):
        self.detection = detection
        self.available = available
        self.reason = reason
    def capabilities(self):
        return Capabilities(self.available, hardware='cpu', reason=self.reason,
                            notes={'model_sha256': 'a' * 64})
    def detect(self, image):
        return self.detection
    def draw_mask(self, polygon, width, height, output):
        Path(output).write_bytes(b'\x89PNG fake')
        return 0.123


def _task_with_image(tmp_path, name='input.png'):
    task = Task.create(tmp_path / 'tasks', name='face')
    img = task.root / 'input' / name
    from PIL import Image
    Image.new('RGB', (64, 80), (10, 20, 30)).save(img)
    return task


def test_polygon_from_landmarks_expands_and_clips():
    lm = fake_landmarks()
    poly = polygon_from_landmarks(lm, 100, 100, FACE_OVAL, 0.0)
    assert len(poly) == len(FACE_OVAL) and all(isinstance(p, tuple) and len(p) == 2 for p in poly)
    big = polygon_from_landmarks(lm, 100, 100, FACE_OVAL, 0.5)
    cx = sum(x for x, _ in poly) / len(poly)
    cbx = sum(x for x, _ in big) / len(big)
    ext0 = max(abs(x - cx) for x, _ in poly)
    ext1 = max(abs(x - cbx) for x, _ in big)
    assert ext1 >= ext0
    for x, y in polygon_from_landmarks(lm, 100, 100, FACE_OVAL, 0.9):
        assert 0 <= x <= 99 and 0 <= y <= 99


def test_polygon_rejects_bad_input():
    with pytest.raises(ValueError):
        polygon_from_landmarks([], 10, 10)
    with pytest.raises(ValueError):
        polygon_from_landmarks([(0.1, 0.1, 0.0)], 10, 10, FACE_OVAL)


def test_face_landmarks_records_model_hash_and_points(tmp_path, monkeypatch):
    task = _task_with_image(tmp_path)
    monkeypatch.setattr(registry, 'get', lambda name: FakeFace(
        {'faces': 1, 'points': 478, 'landmarks': fake_landmarks(),
         'blendshapes': {'jawOpen': 0.2}, 'image_size': [64, 80]}))
    result = engine.face_landmarks(task)
    assert result['status'] == 'pass' and result['points'] == 478
    assert result['model_sha256'] == 'a' * 64 and result['visual_approval'] == 'pending'
    payload = json.loads((task.root / 'face-landmarks.json').read_text())
    assert payload['image_size'] == [64, 80] and len(payload['landmarks']) == 478
    assert Task.open(task.root).entries[-1]['step'] == 'face_landmarks'


def test_face_landmarks_no_face_is_honest_not_retried(tmp_path, monkeypatch):
    task = _task_with_image(tmp_path)
    monkeypatch.setattr(registry, 'get', lambda name: FakeFace({'faces': 0, 'landmarks': []}))
    with pytest.raises(RuntimeError, match='no face'):
        engine.face_landmarks(task)
    entry = Task.open(task.root).entries[-1]
    assert entry['status'] == 'no-face' and entry['faces'] == 0
    assert not (task.root / 'face-landmarks.json').exists()


def test_face_landmarks_unavailable_backend(tmp_path, monkeypatch):
    task = _task_with_image(tmp_path)
    monkeypatch.setattr(registry, 'get', lambda name: FakeFace({}, available=False, reason='install openfigura[face]'))
    with pytest.raises(RuntimeError, match='unavailable'):
        engine.face_landmarks(task)


def test_face_mask_needs_landmarks_first(tmp_path, monkeypatch):
    task = _task_with_image(tmp_path)
    monkeypatch.setattr(registry, 'get', lambda name: FakeFace({'faces': 1}))
    with pytest.raises(FileNotFoundError):
        engine.face_mask(task)


def test_face_mask_writes_png_and_coverage(tmp_path, monkeypatch):
    task = _task_with_image(tmp_path)
    monkeypatch.setattr(registry, 'get', lambda name: FakeFace(
        {'faces': 1, 'points': 478, 'landmarks': fake_landmarks(), 'blendshapes': {},
         'image_size': [64, 80]}))
    engine.face_landmarks(task)
    result = engine.face_mask(task, expand=0.1)
    assert result['status'] == 'pass' and result['coverage'] == 0.123
    assert (task.root / 'input' / 'face-roi.png').is_file()
    with pytest.raises(FileExistsError):
        engine.face_mask(task)


@pytest.mark.parametrize('kwargs', [{'expand': -0.1}, {'expand': 1.5}, {'expand': float('nan')},
                                    {'expand': True}, {'output': 'x.jpg'}, {'output': '../x.png'}])
def test_face_mask_parameter_validation(tmp_path, monkeypatch, kwargs):
    task = _task_with_image(tmp_path)
    monkeypatch.setattr(registry, 'get', lambda name: FakeFace(
        {'faces': 1, 'points': 478, 'landmarks': fake_landmarks(), 'blendshapes': {},
         'image_size': [64, 80]}))
    engine.face_landmarks(task)
    args = {'output': 'face-roi.png', 'expand': 0.06}
    args.update(kwargs)
    with pytest.raises(ValueError):
        engine.face_mask(task, **args)


def test_cli_face_landmarks_and_mask_mirror(tmp_path, monkeypatch, capsys):
    task = _task_with_image(tmp_path)
    monkeypatch.setattr(registry, 'get', lambda name: FakeFace(
        {'faces': 1, 'points': 478, 'landmarks': fake_landmarks(), 'blendshapes': {},
         'image_size': [64, 80]}))
    from openfigura.cli import main
    assert main(['face-landmarks', str(task.root)]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'pass'
    assert main(['face-mask', str(task.root), '--expand', '0.1']) == 0
    assert json.loads(capsys.readouterr().out)['coverage'] == 0.123


def test_executor_face_steps_chain(tmp_path, monkeypatch):
    from openfigura.core.contracts import AssetRef
    task = _task_with_image(tmp_path)
    monkeypatch.setattr(registry, 'get', lambda name: FakeFace(
        {'faces': 1, 'points': 478, 'landmarks': fake_landmarks(), 'blendshapes': {},
         'image_size': [64, 80]}))
    img = task.root / 'input' / 'input.png'
    ref = AssetRef('input/input.png', sha256_file(img), 'image', 'import').to_dict()
    first = engine.execute(task, 'face_landmarks', [ref], {})
    assert first['status'] == 'pass' and first['backend'] == 'mediapipe-face'
    land = next(o for o in first['outputs'] if o['kind'] == 'report')
    second = engine.execute(task, 'face_mask', [ref, land], {'expand': 0.08})
    assert second['status'] == 'pass'
    assert any(o['kind'] == 'mask' for o in second['outputs'])


HEAD = Path.home() / 'Desktop/OpenFigura/golden/cases/head-sculpt/input.png'


@pytest.mark.skipif(not HEAD.is_file(), reason='head-sculpt golden missing')
def test_real_mediapipe_detects_real_face(tmp_path):
    caps = registry.get('mediapipe-face').capabilities()
    if not caps.available:
        pytest.skip('mediapipe runtime or model not provisioned: ' + caps.reason)
    task = Task.create(tmp_path / 'tasks', name='realface')
    import shutil
    shutil.copy2(HEAD, task.root / 'input' / 'input.png')
    result = engine.face_landmarks(task)
    assert result['status'] == 'pass' and result['points'] == 478
    engine.face_mask(task, expand=0.05)
    mask = task.root / 'input' / 'face-roi.png'
    from PIL import Image
    arr = Image.open(mask)
    assert arr.size == (1344, 1792)
    assert result['model_sha256'] == caps.notes['model_sha256']
