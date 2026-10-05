"""Preflight checks with synthetic stdlib-built images."""
from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openfigura.core.preflight import preflight  # noqa: E402


def png(path: Path, w: int, h: int, ctype: int = 6) -> Path:
    ihdr = struct.pack(">IIBBBBB", w, h, 8, ctype, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr
                     + struct.pack(">I", 0) + b"IEND" + struct.pack(">I", 0))
    return path


def test_healthy_portrait_png_alpha_passes(tmp_path):
    r = preflight(png(tmp_path / "ok.png", 1024, 1200))
    assert r["ok"] and not r["errors"]
    assert r["info"]["has_alpha"]


def test_tiny_input_is_hard_error(tmp_path):
    r = preflight(png(tmp_path / "tiny.png", 256, 300))
    assert not r["ok"] and any("256px" in e for e in r["errors"])


def test_sheet_aspect_warns_to_crop_single_view(tmp_path):
    r = preflight(png(tmp_path / "sheet.png", 2048, 800))
    assert r["ok"] and any("multi-view sheet" in w for w in r["warnings"])


def test_extreme_wide_is_error(tmp_path):
    r = preflight(png(tmp_path / "strip.png", 4000, 800))
    assert not r["ok"]


def test_jpeg_warns_about_compression(tmp_path):
    p = tmp_path / "x.jpg"
    p.write_bytes(b"\xff\xd8\xff\xc0" + struct.pack(">H", 17) + b"\x08"
                  + struct.pack(">HH", 900, 1200) + b"\x03" + b"\x00" * 6 + b"\xff\xd9")
    r = preflight(p)
    assert r["ok"] and any("jpeg" in w.lower() for w in r["warnings"])


def test_no_alpha_png_warns(tmp_path):
    r = preflight(png(tmp_path / "opaque.png", 1024, 1024, ctype=2))
    assert r["ok"] and any("alpha" in w for w in r["warnings"])


def test_unsupported_format_is_error(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("not an image")
    r = preflight(p)
    assert not r["ok"] and "unsupported" in r["errors"][0]
