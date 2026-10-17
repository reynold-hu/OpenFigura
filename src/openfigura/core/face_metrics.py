"""Optional face-region metrics for preflight (MediaPipe, external runtime).

Preflight stays cheap by default; this module is only imported and run when
the caller asks for ``face=True`` (CLI ``--face``). MediaPipe, Pillow, NumPy
and the Apache-2.0 face_landmarker model are optional: any missing piece is
reported as ``unavailable`` with the reason, never guessed.

The metrics are advisory: a full-body character sheet legitimately has a small
face, and stylized art may detect no face at all. Warnings are attached by the
preflight caller, not here.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

RESOLUTION = 1024          # generation short/long-edge reference for the estimate
TOUCH_FRACTION = 0.01      # bbox within 1% of the border counts as cropped
SMALL_FACE_PX = 64         # estimated pixels at RESOLUTION below this warns


def _unavailable(reason: str) -> dict:
    return {"status": "unavailable", "reason": reason}


def metrics_from_landmarks(points, width: int, height: int) -> dict:
    """Face bbox and resolution estimate from normalized landmarks only."""
    if not points:
        raise ValueError("landmarks required")
    xs = [float(p[0]) * width for p in points]
    ys = [float(p[1]) * height for p in points]
    x0, x1 = max(0.0, min(xs)), min(float(width), max(xs))
    y0, y1 = max(0.0, min(ys)), min(float(height), max(ys))
    face_w, face_h = max(0.0, x1 - x0), max(0.0, y1 - y0)
    short = min(face_w, face_h)
    fraction = short / min(width, height) if min(width, height) else 0.0
    estimated = short * RESOLUTION / max(width, height) if max(width, height) else 0.0
    touches = (x0 <= width * TOUCH_FRACTION or y0 <= height * TOUCH_FRACTION
               or x1 >= width * (1 - TOUCH_FRACTION)
               or y1 >= height * (1 - TOUCH_FRACTION))
    return {
        "bbox_px": [round(x0, 1), round(y0, 1), round(face_w, 1), round(face_h, 1)],
        "face_width_fraction": round(face_w / width, 6) if width else 0.0,
        "face_height_fraction": round(face_h / height, 6) if height else 0.0,
        "face_short_px": round(short, 1),
        "estimated_face_px_at_1024": round(estimated, 1),
        "touches_border": touches,
        "points": len(points),
    }


def measure(path: Path) -> dict:
    for module in ("mediapipe", "PIL", "numpy"):
        if importlib.util.find_spec(module) is None:
            return _unavailable(f"{module} is not installed (face extra)")
    from openfigura.backends.face_align import MODEL_SHA256, FaceAlignBackend, model_path
    model = model_path()
    if not model.is_file():
        return _unavailable("face_landmarker.task missing; fetch the model and set OPENFIGURA_MEDIAPIPE_MODEL")
    digest = hashlib.sha256(model.read_bytes()).hexdigest()
    if digest != MODEL_SHA256:
        return _unavailable(f"face model sha256 mismatch: {digest[:16]} != {MODEL_SHA256[:16]}")
    try:
        from PIL import Image
        with Image.open(path) as image:
            width, height = image.size
    except Exception as exc:  # noqa: BLE001 - decode failures are explicit
        return _unavailable(f"image could not be decoded: {exc}")
    try:
        result = FaceAlignBackend().detect(path)
    except Exception as exc:  # noqa: BLE001 - mediapipe failures are explicit
        return _unavailable(f"face detection failed: {exc}")
    if result.get("faces", 0) == 0:
        return {"status": "no_face", "faces": 0,
                "image_size": [width, height],
                "note": "stylized or profile art may legitimately detect no face"}
    metrics = metrics_from_landmarks(result["landmarks"], width, height)
    metrics.update(status="measured", faces=1, image_size=[width, height])
    return metrics
