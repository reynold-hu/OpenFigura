"""Mirror-symmetry preflight with synthetic stdlib-built PNG fixtures."""
from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openfigura.core.preflight import preflight  # noqa: E402
from openfigura.core.symmetry import measure_symmetry  # noqa: E402


def chunk(kind: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))


def encode_png(path: Path, width: int, height: int, rows: list[bytes],
               color_type: int = 6, depth: int = 8, interlace: int = 0) -> Path:
    ihdr = struct.pack(">IIBBBBB", width, height, depth, color_type, 0, 0, interlace)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                     + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))
    return path


def mask_rows(width: int, height: int, subject) -> list[bytes]:
    rows = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            inside = subject(x, y)
            row += bytes((200, 30, 30, 255 if inside else 0))
        rows.append(b"\x00" + bytes(row))
    return rows


def header_only_png(path: Path, width: int, height: int, color_type: int = 6,
                    depth: int = 8, interlace: int = 0) -> Path:
    ihdr = struct.pack(">IIBBBBB", width, height, depth, color_type, 0, 0, interlace)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IEND", b""))
    return path


def test_mirror_symmetric_subject_is_measured(tmp_path):
    w = h = 64
    path = encode_png(tmp_path / "sym.png", w, h,
                      mask_rows(w, h, lambda x, y: 8 <= x < w - 8 and 8 <= y < h - 8))
    result = measure_symmetry(path)
    assert result["status"] == "measured"
    assert result["label"] == "mirror-symmetric"
    assert result["mirror_iou"] == 1.0
    assert 0.5 < result["coverage_fraction"] < 0.8


def test_asymmetric_subject_labels_and_warns_in_preflight(tmp_path):
    w, h = 512, 512
    path = encode_png(tmp_path / "asym.png", w, h,
                      mask_rows(w, h, lambda x, y: 10 <= x < w // 2 + 6 and 10 <= y < h - 10))
    result = measure_symmetry(path)
    assert result["label"] == "asymmetric"
    assert result["mirror_iou"] < 0.9
    report = preflight(path)
    assert report["ok"]
    assert any("asymmetric" in warning for warning in report["warnings"])
    assert report["symmetry"]["label"] == "asymmetric"


def test_filter_types_decode_to_the_same_measurement(tmp_path):
    w = h = 32
    plain = encode_png(tmp_path / "plain.png", w, h,
                       mask_rows(w, h, lambda x, y: 4 <= x < w - 4))
    baseline = measure_symmetry(plain)
    # Re-encode with Sub (1) on the first row and Up (2) on the rest: if the
    # unfilter chain is wrong, IoU deviates from the exact mirror pair value.
    raw = bytearray()
    previous = bytes(4 * w)
    for index in range(h):
        row = bytearray()
        for x in range(w):
            inside = 4 <= x < w - 4
            row += bytes((200, 30, 30, 255 if inside else 0))
        if index == 0:
            filtered = bytearray()
            for i, value in enumerate(row):
                left = row[i - 4] if i >= 4 else 0
                filtered.append((value - left) & 0xFF)
            raw += b"\x01" + bytes(filtered)
        else:
            raw += b"\x02" + bytes((value - up) & 0xFF for value, up in zip(row, previous))
        previous = bytes(row)
    filtered_path = encode_png(tmp_path / "filtered.png", w, h, [bytes(raw)])
    result = measure_symmetry(filtered_path)
    assert result["status"] == "measured"
    assert result["label"] == baseline["label"]
    assert result["mirror_iou"] == baseline["mirror_iou"]


def test_grayscale_alpha_is_supported(tmp_path):
    w = h = 32
    rows = []
    for y in range(h):
        row = bytearray()
        for x in range(w):
            inside = 2 <= x < w - 2
            row += bytes((255, 255 if inside else 0))
        rows.append(b"\x00" + bytes(row))
    path = encode_png(tmp_path / "gray.png", w, h, rows, color_type=4)
    result = measure_symmetry(path)
    assert result["status"] == "measured"
    assert result["label"] == "mirror-symmetric"


def test_fully_transparent_reports_no_subject_and_warns(tmp_path):
    w = h = 512
    path = encode_png(tmp_path / "empty.png", w, h,
                      mask_rows(w, h, lambda x, y: False))
    result = measure_symmetry(path)
    assert result["status"] == "measured" and result["label"] == "no-subject"
    report = preflight(path)
    assert report["ok"] and any("transparent" in warning for warning in report["warnings"])


def test_rgb_png_is_unavailable(tmp_path):
    w = h = 32
    rows = []
    for _ in range(h):
        rows.append(b"\x00" + bytes((120, 90, 60)) * w)
    path = encode_png(tmp_path / "rgb.png", w, h, rows, color_type=2)
    result = measure_symmetry(path)
    assert result["status"] == "unavailable" and "alpha channel" in result["reason"]


def test_jpeg_reports_unavailable_without_error(tmp_path):
    path = tmp_path / "x.jpg"
    path.write_bytes(b"\xff\xd8\xff\xc0" + struct.pack(">H", 17) + b"\x08"
                     + struct.pack(">HH", 900, 1200) + b"\x03" + b"\x00" * 6 + b"\xff\xd9")
    report = preflight(path)
    assert report["ok"]
    assert report["symmetry"]["status"] == "unavailable"


def test_interlaced_and_16_bit_are_unavailable(tmp_path):
    interlaced = header_only_png(tmp_path / "i.png", 64, 64, interlace=1)
    assert "interlaced" in measure_symmetry(interlaced)["reason"]
    deep = header_only_png(tmp_path / "d.png", 64, 64, depth=16)
    assert "16-bit" in measure_symmetry(deep)["reason"]


def test_oversized_image_is_refused_before_inflate(tmp_path):
    path = header_only_png(tmp_path / "big.png", 2900, 2900)
    # header-only file: give it a minimal IDAT so the budget check is what rejects it
    ihdr = struct.pack(">IIBBBBB", 2900, 2900, 8, 6, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                     + chunk(b"IDAT", zlib.compress(b"")) + chunk(b"IEND", b""))
    result = measure_symmetry(path)
    assert result["status"] == "unavailable" and "budget" in result["reason"]


def test_existing_header_only_fixtures_stay_unavailable_not_error(tmp_path):
    # Mirrors the historical preflight fixtures: IHDR+IEND without pixels.
    path = header_only_png(tmp_path / "h.png", 1024, 1200)
    report = preflight(path)
    assert report["ok"] and not report["errors"]
    assert report["symmetry"] == {"status": "unavailable", "reason": "no IDAT data"}
