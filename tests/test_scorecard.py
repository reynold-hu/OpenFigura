"""Preliminary scorecard with synthetic stdlib fixtures."""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openfigura.core import engine, face_metrics  # noqa: E402
from openfigura.core.task import Task  # noqa: E402
from test_printability import TETRA, write_glb  # noqa: E402
from test_symmetry import encode_png, mask_rows  # noqa: E402


def add_surface_attributes(path: Path) -> None:
    """Add NORMAL/TEXCOORD/PBR metadata for inspect_glb (data is not re-read)."""
    raw = path.read_bytes()
    (json_size,) = struct.unpack_from("<I", raw, 12)
    doc = json.loads(raw[20:20 + json_size].decode())
    accessors = doc.setdefault("accessors", [])
    accessors.append({"bufferView": 0, "componentType": 5126, "count": 4, "type": "VEC3"})
    accessors.append({"bufferView": 0, "componentType": 5126, "count": 4, "type": "VEC2"})
    primitive = doc["meshes"][0]["primitives"][0]
    primitive["attributes"]["NORMAL"] = len(accessors) - 2
    primitive["attributes"]["TEXCOORD_0"] = len(accessors) - 1
    primitive["material"] = 0
    doc["materials"] = [{"pbrMetallicRoughness": {}}]
    encoded = json.dumps(doc).encode()
    encoded += b" " * (-len(encoded) % 4)
    binchunk = raw[20 + json_size:]
    (bin_size,) = struct.unpack_from("<I", binchunk, 0)
    blob = binchunk[8:8 + bin_size]
    total = 12 + 8 + len(encoded) + 8 + len(blob)
    path.write_bytes(struct.pack("<III", 0x46546C67, 2, total)
                     + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
                     + struct.pack("<II", len(blob), 0x004E4942) + blob)


def task_with_input(tmp_path, name="score", symmetric=True):
    task = Task.create(tmp_path / "tasks", name=name)
    if symmetric:
        rows = mask_rows(512, 512, lambda x, y: 64 <= x < 448 and 64 <= y < 448)
    else:
        rows = mask_rows(512, 512, lambda x, y: 64 <= x < 300 and 64 <= y < 448)
    (task.root / "input").mkdir(exist_ok=True)
    encode_png(task.root / "input" / "input.png", 512, 512, rows)
    write_glb(task.artifact("model.glb"), [TETRA])
    add_surface_attributes(task.artifact("model.glb"))
    return task


def test_scorecard_reports_subscores_and_writes_report(tmp_path):
    task = task_with_input(tmp_path)
    result = engine.score(task, {"build_volume_mm": [2000, 2000, 2000]})
    assert 0 <= result["overall"] <= 100
    assert result["subscores"]["structure"] == 100
    assert result["subscores"]["printability"] == 100
    assert result["subscores"]["input"] is not None
    assert result["subscores"]["evidence"] < 100
    assert result["verdict"] == "needs_work"
    assert result["human_review"]["status"] == "pending"
    assert (task.root / "scorecard.json").is_file()
    entry = Task.open(task.root).entries[-1]
    assert entry["step"] == "score" and entry["report_path"] == "scorecard.json"
    assert json.loads((task.root / "scorecard.json").read_text())["overall"] == result["overall"]


def test_open_mesh_scores_lower_printability_than_closed(tmp_path):
    closed = task_with_input(tmp_path, name="closed")
    closed_result = engine.score(closed)
    open_task = Task.create(tmp_path / "tasks", name="open")
    write_glb(open_task.artifact("model.glb"),
              [{"positions": [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
                              (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)],
                "indices": [0, 1, 2, 0, 2, 3]}])
    open_result = engine.score(open_task)
    assert closed_result["subscores"]["printability"] == 100
    assert open_result["subscores"]["printability"] < 100


def test_asymmetric_input_scores_lower(tmp_path):
    symmetric = engine.score(task_with_input(tmp_path, name="sym", symmetric=True))
    asymmetric = engine.score(task_with_input(tmp_path, name="asym", symmetric=False))
    assert symmetric["subscores"]["input"] > asymmetric["subscores"]["input"]
    assert asymmetric["metrics"]["preflight"]["symmetry"]["label"] == "asymmetric"


def test_build_volume_mismatch_penalizes_printability(tmp_path):
    task = task_with_input(tmp_path)
    mismatch = engine.score(task, {"build_volume_mm": [100, 100, 100]})
    assert mismatch["subscores"]["printability"] == 75
    assert mismatch["metrics"]["printability"]["fits_build_volume"] is False


def test_face_metrics_are_reported_and_scored_without_aesthetics(tmp_path, monkeypatch):
    monkeypatch.setattr(face_metrics, "measure", lambda path: {
        "status": "measured", "faces": 1, "estimated_face_px_at_1024": 40.0,
        "touches_border": True, "bbox_px": [0, 0, 40, 40]})
    task = task_with_input(tmp_path)
    result = engine.score(task, {"face": True})
    assert result["metrics"]["preflight"]["face"]["estimated_face_px_at_1024"] == 40.0
    assert "aesthetics" in result["human_review"]["note"]
    assert result["subscores"]["input"] < 100


def test_score_parameter_validation(tmp_path):
    task = task_with_input(tmp_path)
    with pytest.raises(ValueError, match="unknown score parameter"):
        engine.score(task, {"surprise": 1})
    with pytest.raises(ValueError, match="face must be a boolean"):
        engine.score(task, {"face": "yes"})
    with pytest.raises(ValueError, match="unknown score profile"):
        engine.score(task, {"profile": "cinematic"})


def test_missing_model_is_an_error(tmp_path):
    task = Task.create(tmp_path / "tasks", name="empty")
    with pytest.raises(FileNotFoundError, match="nothing to score"):
        engine.score(task)


def test_cli_and_mcp_mirror_engine(tmp_path, capsys, monkeypatch):
    import asyncio
    from openfigura.cli import main

    task = task_with_input(tmp_path)
    reference = engine.score(task)
    assert main(["score", str(task.root)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["overall"] == reference["overall"]
    assert printed["subscores"] == reference["subscores"]

    pytest.importorskip("mcp")
    from openfigura.mcp_server import build

    async def run():
        app = build()
        result = await app.call_tool("figura_score", {"task_root": str(task.root)})
        if hasattr(result, "content"):
            return json.loads(result.content[0].text)
        return result[1]

    mirrored = asyncio.run(run())
    assert mirrored["overall"] == reference["overall"]
    assert mirrored["verdict"] == reference["verdict"]
