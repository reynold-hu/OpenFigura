"""Versioned, immutable references to verified task-local assets."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, fields
from pathlib import Path, PurePosixPath
from typing import Any


def contract_data(cls: type, data: dict[str, Any]) -> dict[str, Any]:
    """Reject incomplete, extended or unsupported serialized contracts."""
    expected = {field.name for field in fields(cls)} | {'schema_version'}
    if not isinstance(data, dict) or set(data) != expected:
        raise ValueError('contract fields must match the schema exactly')
    if type(data['schema_version']) is not int or data['schema_version'] != 1:
        raise ValueError('unsupported schema_version')
    return {key: value for key, value in data.items() if key != 'schema_version'}


@dataclass(frozen=True)
class AssetRef:
    task_relative_path: str
    sha256: str
    kind: str
    producer_step: str

    def __post_init__(self) -> None:
        path = self.task_relative_path
        if (not isinstance(path, str) or not path or '\\' in path or '\x00' in path
                or PurePosixPath(path).is_absolute()
                or any(part in ('', '.', '..') for part in path.split('/'))
                or re.match(r'^[A-Za-z]:', path)):
            raise ValueError('asset path must be a safe POSIX relative path')
        if not isinstance(self.sha256, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', self.sha256):
            raise ValueError('sha256 must contain exactly 64 hexadecimal characters')
        object.__setattr__(self, 'sha256', self.sha256.lower())
        for name in ('kind', 'producer_step'):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'{name} must be a nonempty string')

    def to_dict(self) -> dict[str, Any]:
        return {'schema_version': 1, **{field.name: getattr(self, field.name) for field in fields(self)}}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AssetRef:
        return cls(**contract_data(cls, data))

    def verify(self, root: Path) -> Path:
        """Resolve within the current task root and verify the actual file hash."""
        resolved_root = Path(root).resolve(strict=True)
        path = resolved_root / self.task_relative_path
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(resolved_root):
            raise ValueError('asset symlink escapes outside task root')
        if not resolved.is_file():
            raise ValueError('asset must be a regular file')
        digest = hashlib.sha256()
        with resolved.open('rb') as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b''):
                digest.update(chunk)
        if digest.hexdigest() != self.sha256:
            raise ValueError('asset hash does not match sha256')
        return path
