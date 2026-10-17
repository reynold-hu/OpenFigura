"""Local printability report with synthetic stdlib-built GLBs."""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openfigura.core import engine  # noqa: E402
from openfigura.core.printability import check_printability  # noqa: E402
from openfigura.core.task import Task  # noqa: E402

TETRA = {
    "positions": [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)],
    "indices": [0, 2, 1, 0, 1, 3, 1, 2, 3, 2, 0, 3],
}


def write_glb(path: Path, primitives: list[dict], nodes: list[dict] | None = None) -> Path:
    blob = bytearray()
    doc = {"asset": {"version": "2.0"},
           "meshes": [{"primitives": []}],
           "accessors": [], "bufferViews": [],
           "buffers": [{"byteLength": 0}]}
    if nodes is not None:
        doc["nodes"] = nodes

    def add_view(payload: bytes) -> int:
        while len(blob) % 4:
            blob.append(0)
        offset = len(blob)
        blob.extend(payload)
        doc["bufferViews"].append({"buffer": 0, "byteOffset": offset,
                                   "byteLength": len(payload)})
        return len(doc["bufferViews"]) - 1

    for spec in primitives:
        positions = spec["positions"]
        payload = b"".join(struct.pack("<fff", *p) for p in positions)
        view = add_view(payload)
        axes = list(zip(*positions))
        doc["accessors"].append({
            "bufferView": view, "componentType": 5126, "count": len(positions),
            "type": "VEC3",
            "min": [min(axis) for axis in axes], "max": [max(axis) for axis in axes],
        })
        primitive = {"attributes": {"POSITION": len(doc["accessors"]) - 1},
                     "mode": spec.get("mode", 4)}
        if spec.get("indices") is not None:
            payload = b"".join(struct.pack("<I", i) for i in spec["indices"])
            view = add_view(payload)
            doc["accessors"].append({"bufferView": view, "componentType": 5125,
                                     "count": len(spec["indices"]), "type": "SCALAR"})
            primitive["indices"] = len(doc["accessors"]) - 1
        doc["meshes"][0]["primitives"].append(primitive)

    while len(blob) % 4:
        blob.append(0)
    doc["buffers"][0]["byteLength"] = len(blob)
    encoded = json.dumps(doc).encode()
    encoded += b" " * (-len(encoded) % 4)
    total = 12 + 8 + len(encoded) + 8 + len(blob)
    path.write_bytes(struct.pack("<III", 0x46546C67, 2, total)
                     + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
                     + struct.pack("<II", len(blob), 0x004E4942) + bytes(blob))
    return path


def test_closed_tetrahedron_passes(tmp_path):
    path = write_glb(tmp_path / "tetra.glb", [TETRA])
    result = check_printability(path)
    assert result["ok"] and result["status"] == "pass"
    assert result["stats"]["triangles"] == 4
    assert result["stats"]["boundary_edges"] == 0
    assert result["stats"]["nonmanifold_edges"] == 0
    assert result["stats"]["shells"] == 1
    assert result["bbox"]["size_m"] == [1.0, 1.0, 1.0]


def test_open_plane_fails_watertight(tmp_path):
    plane = {"positions": [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)],
             "indices": [0, 1, 2, 0, 2, 3]}
    result = check_printability(write_glb(tmp_path / "plane.glb", [plane]))
    assert not result["ok"]
    assert result["stats"]["boundary_edges"] == 4
    assert any("watertight" in error for error in result["errors"])


def test_nonmanifold_edge_is_error(tmp_path):
    fin = {"positions": [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
                         (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0)],
           "indices": [0, 1, 2, 0, 1, 3, 0, 1, 4]}
    result = check_printability(write_glb(tmp_path / "fin.glb", [fin]))
    assert not result["ok"]
    assert result["stats"]["nonmanifold_edges"] == 1
    assert any("non-manifold" in error for error in result["errors"])


def test_degenerate_face_is_error(tmp_path):
    degenerate = {"positions": [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
                  "indices": [0, 1, 2, 0, 1, 1]}
    result = check_printability(write_glb(tmp_path / "degenerate.glb", [degenerate]))
    assert not result["ok"]
    assert result["stats"]["degenerate_faces"] == 1
    assert any("degenerate" in error for error in result["errors"])


def test_duplicate_face_warns(tmp_path):
    duplicate = dict(TETRA)
    duplicate["indices"] = TETRA["indices"] + TETRA["indices"][:3]
    result = check_printability(write_glb(tmp_path / "duplicate.glb", [duplicate]))
    assert result["stats"]["duplicate_faces"] == 1
    assert any("duplicate" in warning for warning in result["warnings"])


def test_two_shells_warn_but_pass(tmp_path):
    offset = {"positions": [(x + 3.0, y, z) for x, y, z in TETRA["positions"]],
              "indices": TETRA["indices"]}
    result = check_printability(write_glb(tmp_path / "two.glb", [TETRA, offset]))
    assert result["ok"]
    assert result["stats"]["shells"] == 2
    assert any("disconnected shells" in warning for warning in result["warnings"])


def test_non_indexed_mesh_is_welded(tmp_path):
    positions = [TETRA["positions"][i] for i in TETRA["indices"]]
    result = check_printability(write_glb(tmp_path / "flat.glb",
                                          [{"positions": positions, "indices": None}]))
    assert result["ok"]
    assert result["stats"]["nonindexed_primitives"] == 1
    assert result["stats"]["boundary_edges"] == 0




def test_split_vertex_closed_mesh_is_watertight(tmp_path):
    # glTF exporters split vertices for normal/UV seams; exact-position welding
    # must recover the closed topology instead of reporting false boundaries.
    indices = TETRA["indices"]
    positions = [TETRA["positions"][i] for i in indices]
    result = check_printability(write_glb(tmp_path / "split.glb",
                                          [{"positions": positions,
                                            "indices": list(range(len(positions)))}]))
    assert result["ok"], result["errors"]
    assert result["stats"]["boundary_edges"] == 0
    assert result["stats"]["raw_vertices"] == 12
    assert result["stats"]["vertices"] == 4


def test_build_volume_fit_and_mismatch(tmp_path):
    path = write_glb(tmp_path / "tetra.glb", [TETRA])
    fits = check_printability(path, build_volume_mm=[2000, 2000, 2000])
    assert fits["stats"]["fits_build_volume"] is True
    too_small = check_printability(path, build_volume_mm=[100, 100, 100])
    assert too_small["stats"]["fits_build_volume"] is False
    assert any("does not fit" in warning for warning in too_small["warnings"])


def test_unsupported_primitive_fails_closed(tmp_path):
    result = check_printability(write_glb(tmp_path / "lines.glb",
                                          [{"positions": [(0.0, 0.0, 0.0)], "mode": 1}]))
    assert not result["ok"]
    assert result["unsupported"]
    assert any("unsupported primitive" in error for error in result["errors"])


def test_transform_is_reported_not_applied(tmp_path):
    result = check_printability(
        write_glb(tmp_path / "moved.glb", [TETRA],
                  nodes=[{"mesh": 0, "translation": [10.0, 0.0, 0.0]}]))
    assert result["ok"]
    assert any("transforms are not applied" in warning for warning in result["warnings"])
    assert result["bbox"]["size_m"] == [1.0, 1.0, 1.0]


def test_invalid_build_volume_rejected(tmp_path):
    path = write_glb(tmp_path / "tetra.glb", [TETRA])
    with pytest.raises(ValueError, match="three positive"):
        check_printability(path, build_volume_mm=[1, 2])
    with pytest.raises(ValueError, match="three positive"):
        check_printability(path, build_volume_mm=[1, 0, 1])


def test_engine_verb_records_report_and_ledger(tmp_path):
    task = Task.create(tmp_path / "tasks", name="print")
    write_glb(task.artifact("model.glb"), [TETRA])
    result = engine.print_check(task, {"build_volume_mm": [2000, 2000, 2000]})
    assert result["ok"] and result["artifact"] == "model.glb"
    assert (task.root / "print-check.json").is_file()
    entry = Task.open(task.root).entries[-1]
    assert entry["step"] == "print-check" and entry["ok"] is True
    assert entry["report_path"] == "print-check.json"
    with pytest.raises(ValueError, match="unknown print-check parameter"):
        engine.print_check(task, {"wall_mm": 1})


def test_cli_and_mcp_mirror_engine(tmp_path, capsys, monkeypatch):
    import asyncio
    from openfigura.cli import main

    task = Task.create(tmp_path / "tasks", name="print")
    write_glb(task.artifact("model.glb"), [TETRA])
    reference = engine.print_check(task)
    assert main(["print-check", str(task.root)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["stats"] == reference["stats"]
    assert printed["ok"] == reference["ok"]

    pytest.importorskip("mcp")
    from openfigura.mcp_server import build

    async def run():
        app = build()
        result = await app.call_tool("figura_print_check",
                                     {"task_root": str(task.root), "artifact": "model.glb"})
        if hasattr(result, "content"):
            return json.loads(result.content[0].text)
        return result[1]

    mirrored = asyncio.run(run())
    assert mirrored["stats"] == reference["stats"]
    assert mirrored["errors"] == reference["errors"]
