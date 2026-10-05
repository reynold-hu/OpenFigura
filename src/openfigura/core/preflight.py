"""Deterministic input-quality preflight: cheap header-level checks that
predict generation failure before a 27-minute backend run is wasted.

Stdlib only (PNG/JPEG headers). Pixel-level checks (foreground coverage,
matte edge quality) are v0.2 items behind the `vision` extra; until then
those constraints are documented warnings, not silent guesses.
"""
from __future__ import annotations

import struct
from pathlib import Path

MIN_EDGE = 512          # below this, 1024-res generation invents detail
GOOD_EDGE = 1024        # matches res default; source below it upscales noise
MAX_ASPECT = 1.8        # wider than this reads as a multi-view sheet, not a portrait
MIN_ASPECT = 0.55       # extremely tall crops lose head/feet context
MAX_BYTES = 25 * 1024 * 1024


def _png_info(data: bytes) -> dict:
    w, h, depth, ctype = struct.unpack_from(">IIBB", data, 16)
    return {"format": "png", "width": w, "height": h, "bit_depth": depth,
            "has_alpha": bool(ctype & 4) or bool(ctype & 8) or bool(ctype & 16)}


def _jpeg_info(data: bytes) -> dict:
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack_from(">HH", data, i + 5)
            return {"format": "jpeg", "width": w, "height": h, "has_alpha": False}
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
        else:
            i += 2 + struct.unpack_from(">H", data, i + 2)[0]
    raise ValueError("no SOF marker in jpeg")


def read_image_info(path: Path) -> dict | None:
    data = Path(path).read_bytes()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        info = _png_info(data)
    elif data[:2] == b"\xff\xd8":
        info = _jpeg_info(data)
    else:
        return None
    info["bytes"] = len(data)
    return info


def preflight(path: Path) -> dict:
    """Returns {ok, errors, warnings, info}. errors => refuse to generate."""
    path = Path(path)
    errors: list[str] = []
    warnings: list[str] = []
    if not path.is_file():
        return {"ok": False, "errors": [f"input not found: {path}"],
                "warnings": [], "info": None}
    info = read_image_info(path)
    if info is None:
        return {"ok": False, "errors": ["unsupported format: use PNG (alpha preferred) or JPEG"],
                "warnings": [], "info": None}
    short = min(info["width"], info["height"])
    aspect = max(info["width"], info["height"]) / short
    if short < MIN_EDGE:
        errors.append(f"short edge {short}px < {MIN_EDGE}px: generation would invent most detail")
    elif short < GOOD_EDGE:
        warnings.append(f"short edge {short}px below res {GOOD_EDGE}: detail will be upscaled")
    if aspect > MAX_ASPECT:
        warnings.append(f"aspect {aspect:.2f}: looks like a multi-view sheet; crop ONE "
                        "character view before generating (single-view backends misread sheets)")
    if aspect > 3.0:
        errors.append(f"aspect {aspect:.2f}: not a usable single subject")
    if info["format"] == "png" and not info["has_alpha"]:
        warnings.append("no alpha channel: solid/complex background will compete with "
                        "the subject; matte it first and keep eyes/ear/highlight regions intact")
    if info["format"] == "jpeg":
        warnings.append("jpeg: compression rings around hair/eyes become 3D bumps; "
                        "PNG from a clean matte is strongly preferred")
    if info["bytes"] > MAX_BYTES:
        warnings.append(f"{info['bytes'] >> 20} MiB input: unusually large, check it is not "
                        "a raw upscaled export with fabricated detail")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "info": info}
