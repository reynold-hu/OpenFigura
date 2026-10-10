"""Reader for MakeHuman CC0 face-unit/viseme target files (thin glue).

Assets live outside the repository (fetched, hashed, never committed):
  faceunits01.zip  d113107bd7eb59f3af4df6fc0ec29bfcc593f496d0b336aec14f086a80ce7146
  visemes02.zip    a69ab6fb95ddd5f56f70acc7e859f5f9c6ae613c527d577ea1571eff2183d29e
from https://files.makehumancommunity.org/functional/ — per-target metadata
declares license CC0. A target file is ASCII lines 'vertexindex dx dy dz'
against the MakeHuman hm08 base mesh; this module only parses and matches
names — applying deltas to a character mesh is a separate, later step.
"""
from __future__ import annotations
import io
import json
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

RUNTIME_DIR = Path.home() / 'Desktop/Local/Opensource/OpenFigura-runtimes/makehuman-expressions'


def pack_path(pack: str) -> Path:
    if pack not in PACK_SHA256:
        raise ValueError(f'unknown pack {pack!r}; known: {sorted(PACK_SHA256)}')
    return Path(os.environ.get('OPENFIGURA_MAKEHUMAN_' + pack.upper(), str(RUNTIME_DIR / (pack + '.zip'))))


def base_mesh_path() -> Path:
    return Path(os.environ.get('OPENFIGURA_MAKEHUMAN_BASE', str(RUNTIME_DIR / 'hm08_base.obj')))

PACK_URLS = {
    'faceunits01': 'https://files.makehumancommunity.org/functional/faceunits01.zip',
    'visemes02': 'https://files.makehumancommunity.org/functional/visemes02.zip',
}
PACK_SHA256 = {
    'faceunits01': 'd113107bd7eb59f3af4df6fc0ec29bfcc593f496d0b336aec14f086a80ce7146',
    'visemes02': 'a69ab6fb95ddd5f56f70acc7e859f5f9c6ae613c527d577ea1571eff2183d29e',
}


@dataclass(frozen=True)
class Target:
    name: str
    license: str
    indices: tuple
    deltas: tuple

    @property
    def max_abs(self) -> float:
        return max((abs(v) for d in self.deltas for v in d), default=0.0)


def parse_target_text(text: str) -> tuple[tuple[int, ...], tuple[tuple[float, float, float], ...]]:
    """Parse ASCII target lines 'index dx dy dz'; reject anything else."""
    indices: list[int] = []
    deltas: list[tuple[float, float, float]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 4:
            raise ValueError(f'target line {number} needs 4 fields, got {len(parts)}')
        try:
            index = int(parts[0])
            delta = tuple(float(v) for v in parts[1:])
        except ValueError as exc:
            raise ValueError(f'target line {number} is not numeric: {exc}') from exc
        if index < 0 or index > 1_000_000:
            raise ValueError(f'target line {number} has implausible vertex index {index}')
        if any(v != v for v in delta):
            raise ValueError(f'target line {number} has NaN delta')
        indices.append(index)
        deltas.append(delta)
    if not indices:
        raise ValueError('empty target')
    if len(set(indices)) != len(indices):
        raise ValueError('duplicate vertex indices in target')
    return tuple(indices), tuple(deltas)


def load_pack(zip_path: Path, expected_sha256: str | None = None) -> dict[str, Target]:
    """Load one MakeHuman functional asset pack into name -> Target."""
    zip_path = Path(zip_path)
    data = zip_path.read_bytes()
    digest = __import__('hashlib').sha256(data).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError(f'pack hash mismatch: {digest} != {expected_sha256}')
    archive = zipfile.ZipFile(io.BytesIO(data))
    metas = {}
    for entry in archive.namelist():
        if entry.startswith('packs/') and entry.endswith('.json'):
            raw = json.loads(archive.read(entry))
            for name, meta in raw.items():
                metas[name.lower()] = meta.get('license') or 'unknown'
    targets: dict[str, Target] = {}
    for entry in archive.namelist():
        if not entry.endswith('.target'):
            continue
        name = Path(entry).stem
        text = archive.read(entry).decode('utf-8', 'replace')
        if not text.strip():
            # Real packs ship zero-delta (neutral) target files; they carry
            # no shape information and are skipped, not treated as errors.
            continue
        indices, deltas = parse_target_text(text)
        license = metas.get(name.lower(), 'unknown')
        targets[name] = Target(name=name, license=license, indices=indices, deltas=deltas)
    if not targets:
        raise ValueError(f'no targets found in {zip_path.name}')
    return targets


def coverage(channels, targets: dict[str, Target]) -> dict:
    """Name-level coverage of MediaPipe blendshape channels by a CC0 pack.

    Case-insensitive matching, but missing/unused lists keep the original
    spelling so the ledger names channels exactly as their source reported
    them.
    """
    names = {name.lower() for name in targets}
    seen = set()
    wanted = []
    for channel in channels:
        key = str(channel).lower()
        if key not in seen:
            seen.add(key)
            wanted.append((str(channel), key))
    missing = sorted(original for original, key in wanted if key not in names)
    matched = len(wanted) - len(missing)
    return {'channels': len(wanted), 'targets': len(names), 'matched': matched,
            'missing_targets': missing,
            'unused_targets': sorted(n for n in names if n not in seen),
            'non_cc0_targets': sorted(n for n, t in targets.items() if t.license.upper() != 'CC0')}
