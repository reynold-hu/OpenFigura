import dataclasses
import hashlib
import json
import shutil

import pytest

from openfigura.core import task as task_module


def contracts():
    from openfigura.core.contracts import AssetRef
    return AssetRef


@pytest.mark.parametrize('change', ['missing', 'unknown', 'version', 'bool_version'])
def test_strict_serialized_fields(change):
    AssetRef = contracts()
    obj = AssetRef('artifacts/a.png', 'a' * 64, 'png', 'render')
    data = obj.to_dict()
    if change == 'missing':
        data.pop(next(k for k in data if k != 'schema_version'))
    elif change == 'unknown':
        data['surprise'] = 1
    else:
        data['schema_version'] = True if change == 'bool_version' else 2
    with pytest.raises((ValueError, TypeError)):
        AssetRef.from_dict(data)


@pytest.mark.parametrize('path', ['', '../a', 'artifacts/../a', '/a', r'artifacts\a',
                                  'C:/a', './a', 'a//b', 'a/', 'a\x00b'])
def test_asset_rejects_unsafe_paths(path):
    AssetRef = contracts()
    with pytest.raises(ValueError):
        AssetRef(path, 'a' * 64, 'png', 'render')


@pytest.mark.parametrize('field,value', [('sha256', 'x' * 64), ('sha256', 'a' * 63),
                                        ('sha256', None), ('kind', ''),
                                        ('producer_step', ''), ('kind', 1)])
def test_asset_rejects_invalid_metadata(field, value):
    AssetRef = contracts()
    data = dict(task_relative_path='artifacts/a.png', sha256='a' * 64,
                kind='png', producer_step='render')
    data[field] = value
    with pytest.raises((ValueError, TypeError)):
        AssetRef(**data)


def test_asset_roundtrip_relocation_and_modified_file(tmp_path):
    AssetRef = contracts()
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
    AssetRef = contracts()
    outside = tmp_path / 'outside'
    outside.write_bytes(b'asset')
    root = tmp_path / 'task'
    root.mkdir()
    (root / 'escaped.png').symlink_to(outside)
    ref = AssetRef('escaped.png', hashlib.sha256(b'asset').hexdigest(), 'png', 'render')
    with pytest.raises(ValueError, match='outside|escape'):
        ref.verify(root)


def test_task_records_contracts_only_after_verification(tmp_path):
    AssetRef = contracts()
    task = task_module.Task.create(tmp_path, 'task')
    ref = AssetRef('artifacts/a.png', hashlib.sha256(b'asset').hexdigest(), 'png', 'render')
    with pytest.raises(FileNotFoundError):
        task.record_asset(ref)
    assert len(task.entries) == 0
    task.artifact('a.png').write_bytes(b'asset')
    task.record_asset(ref)
    reopened = task_module.Task.open(task.root)
    assert reopened.entries[0]['asset'] == ref.to_dict()
    task.artifact('a.png').write_bytes(b'changed')
    with pytest.raises(ValueError):
        task.record_asset(ref)
    assert len(task.entries) == 1
