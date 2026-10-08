import dataclasses
import hashlib
import json
import shutil

import pytest

from openfigura.core import task as task_module


def contracts():
    from openfigura.core.contracts import AssetRef
    from openfigura.core.style import StyleSpec
    return AssetRef, StyleSpec


def style_data():
    return dict(canvas_width=64, canvas_height=96, pixel_scale=2,
                palette=['#112233', '#FFFFFF'], outline_policy='single_pixel',
                shading_policy='stepped', fps=12, anchor='feet',
                transparent_background=True)


def test_style_roundtrip_and_mutation_immunity():
    _, StyleSpec = contracts()
    data = style_data()
    spec = StyleSpec(**data)
    data['palette'].append('#000000')
    assert spec.palette == ('#112233', '#FFFFFF')
    serialized = spec.to_dict()
    assert serialized['schema_version'] == 1
    assert StyleSpec.from_dict(json.loads(json.dumps(serialized))) == spec
    serialized['palette'].append('#000000')
    assert len(spec.palette) == 2
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.fps = 30


@pytest.mark.parametrize('field,value', [
    ('canvas_width', 0), ('canvas_width', 4097), ('canvas_width', True),
    ('canvas_height', 1.5), ('pixel_scale', 0), ('pixel_scale', 17),
    ('pixel_scale', False), ('fps', 0), ('fps', 121), ('fps', True),
    ('palette', []), ('palette', ['#112233'] * 2),
    ('palette', ['112233']), ('palette', ['#GG0000']),
    ('palette', '#112233'), ('palette', [123]),
    ('palette', ['#aabbcc', '#AABBCC']),
    ('palette', [f'#{i:06X}' for i in range(257)]),
    ('outline_policy', 'thick'), ('shading_policy', 'smooth'),
    ('anchor', 'head'), ('transparent_background', 1),
])
def test_style_rejects_invalid_values(field, value):
    _, StyleSpec = contracts()
    data = style_data()
    data[field] = value
    with pytest.raises((ValueError, TypeError)):
        StyleSpec(**data)


@pytest.mark.parametrize('change', ['missing', 'unknown', 'version', 'bool_version'])
@pytest.mark.parametrize('kind', ['asset', 'style'])
def test_strict_serialized_fields(kind, change):
    AssetRef, StyleSpec = contracts()
    cls = AssetRef if kind == 'asset' else StyleSpec
    obj = AssetRef('artifacts/a.png', 'a' * 64, 'png', 'render') if kind == 'asset' else StyleSpec(**style_data())
    data = obj.to_dict()
    if change == 'missing':
        data.pop(next(k for k in data if k != 'schema_version'))
    elif change == 'unknown':
        data['surprise'] = 1
    else:
        data['schema_version'] = True if change == 'bool_version' else 2
    with pytest.raises((ValueError, TypeError)):
        cls.from_dict(data)


@pytest.mark.parametrize('path', ['', '../a', 'artifacts/../a', '/a', r'artifacts\a',
                                  'C:/a', './a', 'a//b', 'a/', 'a\x00b'])
def test_asset_rejects_unsafe_paths(path):
    AssetRef, _ = contracts()
    with pytest.raises(ValueError):
        AssetRef(path, 'a' * 64, 'png', 'render')


@pytest.mark.parametrize('field,value', [('sha256', 'x' * 64), ('sha256', 'a' * 63),
                                        ('sha256', None), ('kind', ''),
                                        ('producer_step', ''), ('kind', 1)])
def test_asset_rejects_invalid_metadata(field, value):
    AssetRef, _ = contracts()
    data = dict(task_relative_path='artifacts/a.png', sha256='a' * 64,
                kind='png', producer_step='render')
    data[field] = value
    with pytest.raises((ValueError, TypeError)):
        AssetRef(**data)


def test_asset_roundtrip_relocation_and_modified_file(tmp_path):
    AssetRef, _ = contracts()
    root = tmp_path / 'task'
    (root / 'artifacts').mkdir(parents=True)
    asset = root / 'artifacts/a.png'
    asset.write_bytes(b'asset')
    ref = AssetRef('artifacts/a.png', hashlib.sha256(b'asset').hexdigest(), 'png', 'render')
    assert AssetRef.from_dict(json.loads(json.dumps(ref.to_dict()))) == ref
    assert ref.verify(root) == asset
    with pytest.raises(dataclasses.FrozenInstanceError):
        ref.kind = 'glb'
    relocated = tmp_path / 'relocated'
    shutil.move(root, relocated)
    assert ref.verify(relocated) == relocated / 'artifacts/a.png'
    (relocated / 'artifacts/a.png').write_bytes(b'changed')
    with pytest.raises(ValueError, match='hash'):
        ref.verify(relocated)


def test_asset_rejects_symlink_escape(tmp_path):
    AssetRef, _ = contracts()
    outside = tmp_path / 'outside'
    outside.write_bytes(b'asset')
    root = tmp_path / 'task'
    root.mkdir()
    (root / 'escaped.png').symlink_to(outside)
    ref = AssetRef('escaped.png', hashlib.sha256(b'asset').hexdigest(), 'png', 'render')
    with pytest.raises(ValueError, match='outside|escape'):
        ref.verify(root)


def test_task_records_contracts_only_after_verification(tmp_path):
    AssetRef, StyleSpec = contracts()
    task = task_module.Task.create(tmp_path, 'task')
    spec = StyleSpec(**style_data())
    task.record_style(spec)
    ref = AssetRef('artifacts/a.png', hashlib.sha256(b'asset').hexdigest(), 'png', 'render')
    with pytest.raises(FileNotFoundError):
        task.record_asset(ref)
    assert len(task.entries) == 1
    task.artifact('a.png').write_bytes(b'asset')
    task.record_asset(ref)
    reopened = task_module.Task.open(task.root)
    assert reopened.entries[0]['style_spec'] == spec.to_dict()
    assert reopened.entries[1]['asset'] == ref.to_dict()
    task.artifact('a.png').write_bytes(b'changed')
    with pytest.raises(ValueError):
        task.record_asset(ref)
    assert len(task.entries) == 2
