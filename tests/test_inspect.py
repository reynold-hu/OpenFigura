"""inspect_glb triangle counting, including non-indexed primitives."""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openfigura.core.inspect import inspect_glb  # noqa: E402
from test_printability import write_glb  # noqa: E402

QUAD_INDEXED = {
    "positions": [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
                  (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)],
    "indices": [0, 1, 2, 0, 2, 3],
}

# Same quad as non-indexed geometry: two triangles listed explicitly.
QUAD_NONINDEXED = {
    "positions": [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0),
                  (0.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)],
}


def _tamper_indices(path: Path, value: int) -> None:
    """Rewrite the JSON chunk's first primitive indices (BIN untouched)."""
    raw = path.read_bytes()
    (json_size,) = struct.unpack_from("<I", raw, 12)
    doc = json.loads(raw[20:20 + json_size].decode())
    doc["meshes"][0]["primitives"][0]["indices"] = value
    encoded = json.dumps(doc).encode()
    encoded += b" " * (-len(encoded) % 4)
    binchunk = raw[20 + json_size:]
    (bin_size,) = struct.unpack_from("<I", binchunk, 0)
    blob = binchunk[8:8 + bin_size]
    total = 12 + 8 + len(encoded) + 8 + len(blob)
    path.write_bytes(struct.pack("<III", 0x46546C67, 2, total)
                     + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
                     + struct.pack("<II", len(blob), 0x004E4942) + blob)


def test_indexed_primitive_counts_triangles(tmp_path):
    report = inspect_glb(write_glb(tmp_path / "quad.glb", [QUAD_INDEXED]))
    assert report["triangles"] == 2


def test_nonindexed_primitive_counts_position_triples(tmp_path):
    report = inspect_glb(write_glb(tmp_path / "nonindexed.glb", [QUAD_NONINDEXED]))
    assert report["triangles"] == 2
    assert "index count not divisible by 3" not in report["problems"]
    assert "index accessor out of range" not in report["problems"]


def test_mixed_indexed_and_nonindexed_sum(tmp_path):
    report = inspect_glb(write_glb(tmp_path / "mixed.glb",
                                   [QUAD_INDEXED, QUAD_NONINDEXED]))
    assert report["triangles"] == 4


def test_malformed_index_count_is_floored_and_flagged(tmp_path):
    bad = {"positions": QUAD_INDEXED["positions"],
           "indices": [0, 1, 2, 0, 2, 3, 0]}
    report = inspect_glb(write_glb(tmp_path / "bad.glb", [bad]))
    assert report["triangles"] == 2
    assert "index count not divisible by 3" in report["problems"]
    assert not report["ok"]


def test_index_accessor_out_of_range_is_flagged(tmp_path):
    path = write_glb(tmp_path / "oor.glb", [QUAD_INDEXED])
    _tamper_indices(path, 99)
    report = inspect_glb(path)
    assert report["triangles"] == 0
    assert "index accessor out of range" in report["problems"]
    assert not report["ok"]
