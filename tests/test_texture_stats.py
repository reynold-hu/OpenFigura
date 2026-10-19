"""Base-color atlas statistics: unavailable paths and a synthetic measured case."""
from __future__ import annotations

import json
import struct
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openfigura.core.texture_stats import base_color_stats  # noqa: E402


def _png_rgb(red: int, green: int, blue: int) -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))
    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    raw = bytes([0, red, green, blue])
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _glb(path: Path, png: bytes | None) -> None:
    if png is None:
        gltf = {"materials": [{"pbrMetallicRoughness": {}}]}
    else:
        gltf = {"materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
                "textures": [{"source": 0}],
                "images": [{"bufferView": 0, "mimeType": "image/png"}],
                "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(png)}],
                "buffers": [{"byteLength": len(png)}]}
    payload = json.dumps(gltf).encode()
    payload += b" " * (-len(payload) % 4)
    binary = png or b""
    total = 12 + 8 + len(payload) + 8 + len(binary)
    path.write_bytes(b"glTF" + struct.pack("<II", 2, total)
                     + struct.pack("<I", len(payload)) + b"JSON" + payload
                     + struct.pack("<I", len(binary)) + b"BIN\x00" + binary)


def test_missing_base_color_texture_is_unavailable(tmp_path):
    target = tmp_path / "plain.glb"
    _glb(target, None)
    result = base_color_stats(target)
    assert result["status"] == "unavailable"
    assert "baseColorTexture" in result["reason"]


def test_measured_black_atlas_reports_dark_fraction(tmp_path):
    pytest.importorskip("PIL")
    pytest.importorskip("numpy")
    target = tmp_path / "black.glb"
    _glb(target, _png_rgb(0, 0, 0))
    result = base_color_stats(target)
    assert result["status"] == "measured"
    assert result["width"] == 1 and result["height"] == 1
    assert result["dark_fraction"] == 1.0
    assert result["mean_rgb"] == [0.0, 0.0, 0.0]
    assert "not a quality verdict" in result["proxy"]
