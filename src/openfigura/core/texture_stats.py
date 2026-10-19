"""Base-color texture statistics as a proxy for painted detail.

These numbers describe the embedded base-color atlas only. They are **not** a
quality verdict: a low dark fraction can be correct for a pale character, and
the near-white fraction includes legitimate padding between UV islands. The
point is to surface "this seed painted no dark brow/iris pigment" as a
measurable difference instead of a human squinting at two renders.
"""
from __future__ import annotations

import hashlib
import io
import json
import struct
from pathlib import Path


def _glb(path: Path) -> tuple[dict, bytes]:
    data = Path(path).read_bytes()
    if data[:4] != b'glTF':
        raise ValueError('not a GLB')
    json_length = struct.unpack('<I', data[12:16])[0]
    doc = json.loads(data[20:20 + json_length])
    bin_start = 20 + json_length
    bin_length = struct.unpack('<I', data[bin_start:bin_start + 4])[0]
    return doc, data[bin_start + 8:bin_start + 8 + bin_length]


def base_color_stats(path: Path) -> dict:
    """Return atlas statistics for the first material's base-color texture."""
    try:
        doc, blob = _glb(path)
    except (OSError, ValueError, struct.error) as exc:
        return {'status': 'unavailable', 'reason': f'unreadable GLB: {exc}'}
    payload = None
    for material in doc.get('materials') or []:
        pbr = material.get('pbrMetallicRoughness') or {}
        texture_ref = pbr.get('baseColorTexture')
        if texture_ref is None:
            continue
        try:
            texture = doc['textures'][texture_ref['index']]
            image = doc['images'][texture['source']]
            view = doc['bufferViews'][image['bufferView']]
        except (KeyError, IndexError, TypeError):
            return {'status': 'unavailable',
                    'reason': 'baseColorTexture references an unreadable image'}
        start = view.get('byteOffset', 0)
        payload = blob[start:start + view['byteLength']]
        break
    if payload is None:
        return {'status': 'unavailable',
                'reason': 'no baseColorTexture in the first material'}
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        return {'status': 'unavailable', 'reason': 'Pillow/NumPy not installed'}
    try:
        image = Image.open(io.BytesIO(payload)).convert('RGB')
        array = np.asarray(image).astype(np.int16)
        luminance = array.mean(axis=2)
        return {
            'status': 'measured',
            'sha256': hashlib.sha256(payload).hexdigest(),
            'width': image.width, 'height': image.height,
            'mean_rgb': [round(float(v), 1) for v in array.reshape(-1, 3).mean(axis=0)],
            'dark_fraction': round(float((luminance < 60).mean()), 5),
            'near_white_fraction': round(float((luminance > 245).mean()), 5),
            'proxy': 'atlas statistics only; not a quality verdict',
        }
    except (OSError, ValueError) as exc:
        return {'status': 'unavailable', 'reason': f'unreadable image: {exc}'}
