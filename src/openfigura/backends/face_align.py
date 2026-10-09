"""Optional MediaPipe FaceLandmarker runtime (Tasks API).

MediaPipe code and the shipped float16 face_landmarker model are Apache-2.0;
the model asset is fetched by the user, never committed, and its SHA-256 is
recorded in every ledger entry that uses it. Heavy imports stay inside
methods so `openfigura backends` never loads TensorFlow Lite.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from openfigura.core import registry
from openfigura.core.registry import Capabilities

MODEL_URL = ('https://storage.googleapis.com/mediapipe-models/face_landmarker/'
             'face_landmarker/float16/1/face_landmarker.task')
MODEL_SHA256 = '64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff'
# Ordered facial-oval loop from the upstream FaceMesh canonical contour set.
FACE_OVAL = (10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397,
             365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58,
             132, 93, 234, 127, 162, 21, 54, 103, 67, 109)
# Ordered loops for lips and irises, same upstream vocabulary (refine passes).
LIPS_OUTER = (61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 61, 185, 40,
              39, 37, 0, 267, 269, 270, 409, 292)
IRIS_RIGHT = (468, 469, 470, 471, 472)
IRIS_LEFT = (473, 474, 475, 476, 477)


def model_path() -> Path:
    return Path(os.environ.get('OPENFIGURA_MEDIAPIPE_MODEL',
                               str(Path.home() / 'Desktop/Local/Opensource/OpenFigura-runtimes/mediapipe/face_landmarker.task')))


def polygon_from_landmarks(landmarks, width: int, height: int, indices=FACE_OVAL,
                           expand: float = 0.0):
    """Return an integer pixel polygon for one upstream landmark loop.

    `expand` grows the loop outward from its centre as a fraction of its own
    half-extent, so a tight facial oval still covers ears-adjacent seams.
    """
    if not landmarks:
        raise ValueError('landmarks required')
    if any(index >= len(landmarks) for index in indices):
        raise ValueError('landmark loop index out of range for this point count')
    pts = [(landmarks[index][0] * width, landmarks[index][1] * height) for index in indices]
    cx = sum(x for x, _ in pts) / len(pts)
    cy = sum(y for _, y in pts) / len(pts)
    extent = max(max(abs(x - cx) for x, _ in pts), max(abs(y - cy) for _, y in pts)) or 1.0
    factor = 1.0 + max(0.0, min(1.0, expand)) * (1.0 if extent > 0 else 0.0)
    out = []
    for x, y in pts:
        px = cx + (x - cx) * factor
        py = cy + (y - cy) * factor
        out.append((min(max(px, 0.0), width - 1.0), min(max(py, 0.0), height - 1.0)))
    return [(int(round(x)), int(round(y))) for x, y in out]


class FaceAlignBackend:
    id = 'mediapipe-face'
    kind = 'generate'

    def capabilities(self) -> Capabilities:
        if importlib.util.find_spec('mediapipe') is None:
            return Capabilities(False, hardware='cpu',
                                reason="install openfigura[face]: 'mediapipe' package missing")
        path = model_path()
        if not path.is_file():
            return Capabilities(False, hardware='cpu',
                                reason='face_landmarker.task missing; fetch MODEL_URL and record OPENFIGURA_MEDIAPIPE_MODEL')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != MODEL_SHA256:
            return Capabilities(False, hardware='cpu',
                                reason=f'model sha256 mismatch: {digest[:16]} != expected {MODEL_SHA256[:16]}')
        probe = subprocess.run([sys.executable, '-c',
                                'from mediapipe.tasks.python import vision;print("MP_OK")'],
                               capture_output=True, text=True, timeout=120)
        ok = probe.returncode == 0 and 'MP_OK' in probe.stdout
        reason = '' if ok else 'mediapipe Tasks API import failed: ' + (probe.stderr or probe.stdout or '')[-300:]
        return Capabilities(ok, hardware='cpu', reason=reason,
                            notes={'license': 'code+model Apache-2.0', 'model': str(path),
                                   'model_sha256': digest,
                                   'limits': 'realistic frontal faces; stylized/profile inputs may detect zero faces'})

    def detect(self, image: Path) -> dict:
        import numpy as np
        import mediapipe as mp
        from PIL import Image
        from mediapipe.tasks import python as mpt
        from mediapipe.tasks.python import vision
        path = model_path()
        arr = np.asarray(Image.open(image).convert('RGB'))
        options = vision.FaceLandmarkerOptions(
            base_options=mpt.BaseOptions(model_asset_path=str(path)),
            running_mode=vision.RunningMode.IMAGE, num_faces=1,
            output_face_blendshapes=True)
        landmarker = vision.FaceLandmarker.create_from_options(options)
        try:
            result = landmarker.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=arr))
        finally:
            landmarker.close()
        if not result.face_landmarks:
            return {'faces': 0, 'landmarks': [], 'blendshapes': []}
        face = result.face_landmarks[0]
        points = [(lm.x, lm.y, getattr(lm, 'z', 0.0) or 0.0) for lm in face]
        blend = ({} if not result.face_blendshapes else
                 {b.category_name: round(float(b.score), 4) for b in result.face_blendshapes[0]})
        return {'faces': 1, 'points': len(points), 'landmarks': points,
                'blendshapes': blend, 'image_size': [int(arr.shape[1]), int(arr.shape[0])]}


    def draw_mask(self, polygon: list, width: int, height: int, output: Path) -> float:
        """Rasterise a landmark polygon into an L-mode PNG; return mean coverage 0..1."""
        import numpy as np
        from PIL import Image, ImageDraw
        if width <= 0 or height <= 0:
            raise ValueError('mask dimensions must be positive')
        if len(polygon) < 3:
            raise ValueError('polygon needs at least three points')
        mask = Image.new('L', (width, height), 0)
        ImageDraw.Draw(mask).polygon([tuple(p) for p in polygon], fill=255)
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        mask.save(output)
        return float(np.asarray(mask).mean() / 255.0)


registry.register('mediapipe-face', FaceAlignBackend,
                  'MediaPipe FaceLandmarker 478-point CPU detection (Apache-2.0 model, user-fetched)')
