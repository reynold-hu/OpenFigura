"""Stdlib silhouette symmetry measurement for preflight (PNG only).

Predicts whether a reference's matte is usable for mirror-based workflows
(symmetry checks, mirrored retopo, left/right texture projection). This is a
heuristic measurement, never an acceptance gate: it decodes the alpha channel,
mirrors it around the vertical axis and reports intersection-over-union of the
subject silhouettes at a bounded sampling stride.

Honest limits, by design:

- Only 8-bit non-interlaced PNG with an alpha channel (color type 4 or 6) is
  decodable here; anything else reports ``unavailable`` with the reason
  instead of guessing (JPEG has no stdlib decoder in this project).
- The decode is bounded to ``SYMMETRY_MAX_PIXELS`` pixels before inflating;
  larger inputs report ``unavailable`` rather than slowing preflight down.
  Filtering is sequential per spec (Paeth/Up rows depend on the previous row),
  so the whole image is decompressed even though only sampled pixels are
  compared. Measured 2026-10-16 (evidence: .local/runs/2026-10-16-borrow-batch/):
  a 6.2MP RGBA matte decodes and measures in ~1.1 s, 6.1MP in ~2.0 s.
- Thresholds for labels are OpenFigura's own heuristic (documented below) and
  carry no external authority.
"""
from __future__ import annotations

import struct
import zlib

SYMMETRY_MAX_PIXELS = 8_388_608          # 8MP (e.g. 2896x2896); decode budget, pre-inflate
SYMMETRY_MAX_RAW_BYTES = 48 * 1024 * 1024
SAMPLING_TARGET_EDGE = 512               # sampled grid edge, bounded pair count
ALPHA_THRESHOLD = 8                      # alpha >= 8 counts as subject

# Heuristic label cuts over the sampled mirror IoU. Advisory only.
SYMMETRIC_IOU = 0.98
ROUGHLY_SYMMETRIC_IOU = 0.90

_CHANNELS = {4: 2, 6: 4}


def _chunks(data: bytes):
    offset = 8
    while offset + 8 <= len(data):
        (length,) = struct.unpack_from(">I", data, offset)
        kind = data[offset + 4:offset + 8]
        if offset + 12 + length > len(data):
            raise ValueError("truncated PNG chunk")
        yield kind, data[offset + 8:offset + 8 + length]
        offset += 12 + length


def _unavailable(reason: str) -> dict:
    return {"status": "unavailable", "reason": reason}


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _unfilter(raw: bytes, width: int, height: int, bpp: int) -> list[bytes]:
    stride = width * bpp
    rows: list[bytes] = []
    previous = bytes(stride)
    offset = 0
    for _ in range(height):
        if offset >= len(raw):
            raise ValueError("truncated PNG image data")
        kind = raw[offset]
        line = raw[offset + 1:offset + 1 + stride]
        offset += 1 + stride
        if len(line) != stride:
            raise ValueError("truncated PNG scanline")
        if kind == 0:
            row = line
        elif kind == 2:
            row = bytes((value + up) & 0xFF for value, up in zip(line, previous))
        else:
            out = bytearray(stride)
            if kind == 1:
                for index, value in enumerate(line):
                    left = out[index - bpp] if index >= bpp else 0
                    out[index] = (value + left) & 0xFF
            elif kind == 3:
                for index, value in enumerate(line):
                    left = out[index - bpp] if index >= bpp else 0
                    out[index] = (value + ((left + previous[index]) >> 1)) & 0xFF
            elif kind == 4:
                for index, value in enumerate(line):
                    left = out[index - bpp] if index >= bpp else 0
                    upper_left = previous[index - bpp] if index >= bpp else 0
                    out[index] = (value + _paeth(left, previous[index], upper_left)) & 0xFF
            else:
                raise ValueError(f"unknown PNG filter type {kind}")
            row = bytes(out)
        rows.append(row)
        previous = row
    return rows


def measure_symmetry(path) -> dict:
    """Mirror-IoU of the PNG alpha silhouette; ``unavailable`` is explicit."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        return _unavailable(f"cannot read input: {exc}")
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return _unavailable("symmetry measurement currently supports PNG only")
    header = None
    idat = bytearray()
    try:
        for kind, payload in _chunks(data):
            if kind == b"IHDR":
                header = payload
            elif kind == b"IDAT":
                idat += payload
            elif kind == b"IEND":
                break
    except ValueError as exc:
        return _unavailable(str(exc))
    if header is None or len(header) != 13:
        return _unavailable("missing or malformed IHDR")
    width, height, depth, color_type, compression, filtering, interlace = \
        struct.unpack(">IIBBBBB", header)
    if (width, height) == (0, 0):
        return _unavailable("empty image")
    if compression or filtering:
        return _unavailable("unsupported PNG compression or filter method")
    if interlace:
        return _unavailable("interlaced PNG is not measured")
    if depth != 8:
        return _unavailable(f"{depth}-bit PNG is not measured (8-bit required)")
    channels = _CHANNELS.get(color_type)
    if channels is None:
        return _unavailable("silhouette symmetry needs an alpha channel (color type 4 or 6)")
    if width * height > SYMMETRY_MAX_PIXELS:
        return _unavailable(f"{width}x{height} exceeds the {SYMMETRY_MAX_PIXELS}-pixel decode budget")
    if not idat:
        return _unavailable("no IDAT data")
    expected = height * (1 + width * channels)
    if expected > SYMMETRY_MAX_RAW_BYTES:
        return _unavailable("decompressed image exceeds the raw byte budget")
    try:
        decompressor = zlib.decompressobj()
        raw = decompressor.decompress(bytes(idat), SYMMETRY_MAX_RAW_BYTES + 1)
        raw += decompressor.flush()
    except zlib.error as exc:
        return _unavailable(f"zlib decode failed: {exc}")
    if len(raw) > SYMMETRY_MAX_RAW_BYTES:
        return _unavailable("decompressed image exceeds the raw byte budget")
    try:
        rows = _unfilter(raw, width, height, channels)
    except ValueError as exc:
        return _unavailable(str(exc))
    alpha_offset = 3 if channels == 4 else 1
    stride = max(1, -(-max(width, height) // SAMPLING_TARGET_EDGE))
    inter = union = subject = total = 0
    for y in range(0, height, stride):
        row = rows[y]
        for x in range(0, (width + 1) // 2, stride):
            mirrored = width - 1 - x
            here = row[x * channels + alpha_offset] >= ALPHA_THRESHOLD
            if mirrored == x:
                inter += 1 if here else 0
                union += 1 if here else 0
                subject += 1 if here else 0
                total += 1
                continue
            there = row[mirrored * channels + alpha_offset] >= ALPHA_THRESHOLD
            total += 2
            if here and there:
                inter += 1
                union += 1
                subject += 2
            elif here or there:
                union += 1
                subject += 1
    if union == 0:
        return {"status": "measured", "label": "no-subject", "mirror_iou": None,
                "coverage_fraction": 0.0, "sampled_pairs": total, "stride": stride,
                "source": "alpha>=8",
                "note": "alpha channel is fully transparent below the subject threshold"}
    iou = inter / union
    if iou >= SYMMETRIC_IOU:
        label = "mirror-symmetric"
    elif iou >= ROUGHLY_SYMMETRIC_IOU:
        label = "roughly-symmetric"
    else:
        label = "asymmetric"
    return {"status": "measured", "label": label, "mirror_iou": round(iou, 4),
            "coverage_fraction": round(subject / total, 4),
            "sampled_pairs": total, "stride": stride, "source": "alpha>=8",
            "note": "heuristic silhouette mirror check over sampled pixel pairs; advisory only"}
