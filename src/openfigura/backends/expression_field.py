"""Pure-numpy expression delta fields: hm08 base mesh -> character vertices.

Nearest-base-vertex sampling (documented approximation, not barycentric):
the hm08 base mesh carries 19,158 vertices with face-region spacing of a few
millimetres, which is finer than the millimetre-scale ARKit deltas we move.
A Gaussian-style falloff (2 cm sigma) fades deltas as the character surface
departs from the base, so body regions far from any expression vertex stay
put. No Blender import here — fully unit-testable on a bare machine.
"""
from __future__ import annotations
import numpy as np

FALLOFF_SIGMA = 0.02


def load_obj_positions(path) -> np.ndarray:
    """Parse 'v x y z' lines of an OBJ into an (N,3) float array."""
    rows = []
    with open(path, 'r', encoding='utf-8', errors='replace') as handle:
        for line in handle:
            if line.startswith('v '):
                parts = line.split()
                if len(parts) >= 4:
                    rows.append([float(parts[1]), float(parts[2]), float(parts[3])])
    if not rows:
        raise ValueError(f'no vertices parsed from {path}')
    return np.asarray(rows, dtype=np.float64)


def dense_deltas(target, vertex_count: int) -> np.ndarray:
    """Expand a sparse Target into a (vertex_count,3) zero-based field."""
    if target.indices and max(target.indices) >= vertex_count:
        raise ValueError(f'target {target.name} references vertex '
                         f'{max(target.indices)} beyond base mesh ({vertex_count} vertices)')
    field = np.zeros((vertex_count, 3), dtype=np.float64)
    field[list(target.indices)] = np.asarray(target.deltas, dtype=np.float64)
    return field


def nearest_map(base_positions: np.ndarray, character_positions: np.ndarray) -> dict:
    """One shared nearest-base-vertex mapping for all channels (tree built once)."""
    from scipy.spatial import cKDTree
    tree = cKDTree(base_positions)
    distances, indices = tree.query(character_positions, k=1)
    falloff = np.exp(-np.square(np.asarray(distances) / FALLOFF_SIGMA))
    return {'indices': np.asarray(indices, dtype=np.int64),
            'distances': np.asarray(distances, dtype=np.float64),
            'falloff': falloff}


def sample_field(dense: np.ndarray, mapping: dict) -> np.ndarray:
    """Sample a base-mesh (N,3) field onto character vertices via nearest_map."""
    if dense.shape[0] <= int(mapping['indices'].max()):
        raise ValueError('mapping references vertices beyond this field')
    return dense[list(mapping['indices'])] * mapping['falloff'][:, None]


def compose(fields, scores: dict, intensity: float = 1.0) -> np.ndarray:
    """Weighted sum of per-channel character fields, scaled by intensity.

    `fields` maps channel name -> (M,3) array; `scores` maps the same names
    to 0..1 blendshape weights from the reference photo.
    """
    if not fields:
        raise ValueError('no channels to compose')
    sample = next(iter(fields.values()))
    total = np.zeros_like(sample, dtype=np.float64)
    for channel, field in fields.items():
        weight = float(scores.get(channel, 0.0))
        if weight:
            total += field * weight
    return total * float(intensity)
