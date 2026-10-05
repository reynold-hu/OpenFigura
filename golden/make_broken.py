#!/usr/bin/env python3
"""Maintainer tool: derive broken inputs from committed good cases.

We never prompt AIGC models for bad inputs — degradation must be exact,
reproducible and attributable to one mechanism per case:

  broken-tiny   256px short edge   -> preflight ERROR (below 512 floor)
  broken-sheet  3x side-by-side    -> preflight ERROR (aspect > 3, not one subject)
  broken-jpeg   25% quality JPEG   -> preflight WARNING (compression rings)

Uses only stdlib + `sips` (macOS built-in). Run from golden/:

  python3 make_broken.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASES = HERE / "cases"


def sips(argv: list[str]) -> None:
    subprocess.run(["sips", *argv], check=True, capture_output=True)


def png_dims(path: Path) -> tuple[int, int]:
    import struct
    data = path.read_bytes()
    return struct.unpack_from(">II", data, 16)


def write_case(name: str, digest_src: Path, axis: str, expect: str) -> None:
    d = CASES / name
    d.mkdir(exist_ok=True)
    case = {
        "name": name,
        "axis": axis,
        "derived_from": digest_src,
        "expect_preflight": expect,
        "expect_input_sha256": hashlib.sha256((d / "input.png").read_bytes()).hexdigest()
        if (d / "input.png").exists() else None,
        "note": "gate test: run_golden must FAIL/WARN here by design; never generate from this",
    }
    if (d / "input.jpg").exists():
        case["expect_input_sha256"] = hashlib.sha256((d / "input.jpg").read_bytes()).hexdigest()
    (d / "case.json").write_text(json.dumps(case, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    # 1. tiny: xiaoman-front -> 256px short edge (ERROR expected)
    src = CASES / "xiaoman-front" / "input.png"
    out = CASES / "broken-tiny"
    out.mkdir(exist_ok=True)
    sips(["-Z", "256", str(src), "--out", str(out / "input.png")])
    write_case("broken-tiny", "xiaoman-front/input.png",
               "resolution floor", "error")

    # 2. sheet: scifi-stride x4 horizontally (4*1312/1696 = aspect 3.09 -> ERROR)
    src = CASES / "scifi-stride" / "input.png"
    out = CASES / "broken-sheet"
    out.mkdir(exist_ok=True)
    canvas = out / "input.png"
    _concat_png_h(src, src, src, src, canvas)
    write_case("broken-sheet", "scifi-stride/input.png",
               "multi-view strip masquerading as one subject", "error")

    # 3. jpeg: silver-scarf at 25% quality (WARNING expected)
    src = CASES / "silver-scarf" / "input.png"
    out = CASES / "broken-jpeg"
    out.mkdir(exist_ok=True)
    sips(["-s", "format", "jpeg", "-s", "formatOptions", "25", str(src),
          "--out", str(out / "input.jpg")])
    (out / "input.png").unlink(missing_ok=True) if (out / "input.png").exists() else None
    write_case("broken-jpeg", "silver-scarf/input.png",
               "compression artifacts become 3D bumps", "warn")
    print("broken cases written")


def _concat_png_h(*paths: Path) -> None:
    """Pure-stdlib horizontal PNG concat (RGB/RGBA 8-bit, non-interlaced)."""
    import struct
    import zlib

    imgs = []
    for p in paths[:-1]:
        data = p.read_bytes()
        pos, idat, w, h, ctype = 8, b"", 0, 0, 0
        while pos < len(data):
            ln, typ = struct.unpack_from(">I4s", data, pos)
            chunk = data[pos + 8: pos + 8 + ln]
            if typ == b"IHDR":
                w, h, depth, ctype, _, _, _ = struct.unpack_from(">IIBBBBB", chunk, 0)
                assert depth == 8 and ctype in (2, 6), f"unsupported png {p}"
            elif typ == b"IDAT":
                idat += chunk
            elif typ == b"IEND":
                break
            pos += 12 + ln
        ch = 4 if ctype == 6 else 3
        raw = zlib.decompress(idat)
        stride = w * ch + 1
        rows = [raw[i * stride + 1:(i + 1) * stride] for i in range(h)]
        imgs.append((w, h, ch, rows))

    W = sum(i[0] for i in imgs)
    H = max(i[1] for i in imgs)
    ch = imgs[0][2]
    out_rows = []
    for y in range(H):
        row = b""
        for iw, ih, ich, rows in imgs:
            row += rows[y][:(iw * ch)] if y < ih else bytes(iw * ch)
        out_rows.append(b"\x00" + row)
    comp = zlib.compress(b"".join(out_rows), 6)
    ctype = 6 if ch == 4 else 2

    def chunk(tag: bytes, payload: bytes) -> bytes:
        c = struct.pack(">I", len(payload)) + tag + payload
        return c + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)

    paths[-1].write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, ctype, 0, 0, 0))
        + chunk(b"IDAT", comp) + chunk(b"IEND", b""))


if __name__ == "__main__":
    main()
