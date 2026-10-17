"""Face-region metrics and the optional preflight face section."""
from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openfigura.core import face_metrics  # noqa: E402
from openfigura.core.preflight import preflight  # noqa: E402


def chunk(kind: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))


def png(path: Path, width: int, height: int) -> Path:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    rows = b"".join(b"\x00" + bytes((200, 30, 30, 255)) * width for _ in range(height))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                     + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
    return path


def test_metrics_from_landmarks_bbox_fraction_and_estimate():
    points = [(0.4, 0.4), (0.6, 0.4), (0.4, 0.5), (0.6, 0.5)]
    result = face_metrics.metrics_from_landmarks(points, 1000, 2000)
    assert result["bbox_px"] == [400.0, 800.0, 200.0, 200.0]
    assert result["face_short_px"] == 200.0
    assert result["face_width_fraction"] == 0.2
    assert result["estimated_face_px_at_1024"] == 102.4
    assert result["touches_border"] is False


def test_metrics_from_landmarks_detects_border_touch():
    points = [(0.005, 0.4), (0.2, 0.4), (0.005, 0.5), (0.2, 0.5)]
    result = face_metrics.metrics_from_landmarks(points, 1000, 1000)
    assert result["touches_border"] is True


def test_preflight_face_is_off_by_default(tmp_path):
    report = preflight(png(tmp_path / "in.png", 512, 512))
    assert report["face"] == {"status": "not_requested"}


def test_preflight_face_warns_on_small_and_cropped(tmp_path, monkeypatch):
    monkeypatch.setattr(face_metrics, "measure", lambda path: {
        "status": "measured", "faces": 1, "estimated_face_px_at_1024": 40.0,
        "touches_border": True, "bbox_px": [0, 0, 40, 40],
    })
    report = preflight(png(tmp_path / "in.png", 512, 512), face=True)
    assert report["face"]["status"] == "measured"
    assert any("facial features" in warning for warning in report["warnings"])
    assert any("touches the image border" in warning for warning in report["warnings"])


def test_preflight_face_no_face_is_not_a_warning(tmp_path, monkeypatch):
    monkeypatch.setattr(face_metrics, "measure", lambda path: {
        "status": "no_face", "faces": 0, "image_size": [512, 512]})
    report = preflight(png(tmp_path / "in.png", 512, 512), face=True)
    assert report["face"]["status"] == "no_face"
    assert not any("face" in warning.lower() for warning in report["warnings"])


def test_preflight_face_unavailable_keeps_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(face_metrics, "measure", lambda path: {
        "status": "unavailable", "reason": "mediapipe is not installed (face extra)"})
    report = preflight(png(tmp_path / "in.png", 512, 512), face=True)
    assert report["face"]["status"] == "unavailable"
    assert "mediapipe" in report["face"]["reason"]
