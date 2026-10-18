"""Final evaluation report plumbing, with injected external validators."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openfigura.core import engine, external_validation  # noqa: E402
from openfigura.core.task import Task  # noqa: E402
from test_scorecard import task_with_input  # noqa: E402

GLTF_FAKE = {
    "status": "validated",
    "validator": "gltf-validator",
    "issues": {"numErrors": 0, "numWarnings": 1, "numInfos": 0, "numHints": 0,
               "messages": [{"code": "UNUSED_OBJECT", "severity": 1,
                             "message": "unused object", "pointer": "/materials/0"}]},
    "wall_seconds": 0.1,
}
TRIMESH_FAKE = {
    "status": "validated", "trimesh_version": "4.0.0",
    "vertices": 4, "faces": 4, "degenerate_faces": 0,
    "is_watertight": True, "is_winding_consistent": True, "is_volume": True,
    "components": 1, "euler_number": 2, "area_m2": 2.4, "volume_m3": 0.16,
    "extents_m": [1.0, 1.0, 1.0], "wall_seconds": 0.2,
}


def fake_externals(monkeypatch):
    monkeypatch.setattr(external_validation, "gltf_validator", lambda model: dict(GLTF_FAKE))
    monkeypatch.setattr(external_validation, "trimesh_check", lambda model: dict(TRIMESH_FAKE))


def test_evaluation_writes_json_and_markdown_with_external_results(tmp_path, monkeypatch):
    fake_externals(monkeypatch)
    task = task_with_input(tmp_path)
    result = engine.evaluate(task, {"build_volume_mm": [2000, 2000, 2000]})
    assert result["scorecard"]["verdict"] == "needs_work"
    assert result["external"]["gltf_validator"]["status"] == "validated"
    assert result["external"]["trimesh"]["is_watertight"] is True
    assert result["reports"]["markdown"] == "evaluation-report.md"
    report = (task.root / "evaluation-report.md").read_text()
    assert "# Evaluation report" in report
    assert "glTF-Validator — validated" in report
    assert "trimesh — validated" in report
    assert "Human handoff (pending)" in report
    assert "UNUSED_OBJECT" in report
    saved = json.loads((task.root / "evaluation.json").read_text())
    assert saved["external"]["trimesh"]["components"] == 1
    entry = Task.open(task.root).entries[-1]
    assert entry["step"] == "evaluate"
    assert entry["external"] == {"gltf_validator": "validated", "trimesh": "validated"}
    assert entry["report"] == "evaluation-report.md"


def test_external_can_be_skipped(tmp_path):
    task = task_with_input(tmp_path)
    result = engine.evaluate(task, {"external": False})
    assert result["external"]["gltf_validator"]["status"] == "skipped"
    assert result["external"]["trimesh"]["status"] == "skipped"
    assert "glTF-Validator — skipped" in (task.root / "evaluation-report.md").read_text()


def test_missing_runtimes_are_unavailable_not_fatal(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENFIGURA_GLTF_VALIDATOR_MODULE", raising=False)
    monkeypatch.delenv("OPENFIGURA_TRIMESH_PYTHON", raising=False)
    task = task_with_input(tmp_path)
    result = engine.evaluate(task)
    assert result["external"]["gltf_validator"]["status"] == "unavailable"
    assert "OPENFIGURA_GLTF_VALIDATOR_MODULE" in result["external"]["gltf_validator"]["reason"]
    assert result["external"]["trimesh"]["status"] == "unavailable"
    assert "OPENFIGURA_TRIMESH_PYTHON" in result["external"]["trimesh"]["reason"]
    report = (task.root / "evaluation-report.md").read_text()
    assert "not measured, not passed" in report


def test_evaluate_rejects_unknown_parameters(tmp_path):
    task = task_with_input(tmp_path)
    with pytest.raises(ValueError, match="unknown score parameter"):
        engine.evaluate(task, {"surprise": 1})
    with pytest.raises(ValueError, match="external must be a boolean"):
        engine.evaluate(task, {"external": "yes"})


def test_cli_and_mcp_mirror_evaluate(tmp_path, capsys, monkeypatch):
    import asyncio
    from openfigura.cli import main

    fake_externals(monkeypatch)
    task = task_with_input(tmp_path)
    reference = engine.evaluate(task, {"external": False})
    assert main(["evaluate", str(task.root), "--params", '{"external": false}']) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["scorecard"]["overall"] == reference["scorecard"]["overall"]

    pytest.importorskip("mcp")
    from openfigura.mcp_server import build

    async def run():
        app = build()
        result = await app.call_tool("figura_evaluate",
                                     {"task_root": str(task.root),
                                      "params": {"external": False}})
        if hasattr(result, "content"):
            return json.loads(result.content[0].text)
        return result[1]

    mirrored = asyncio.run(run())
    assert mirrored["scorecard"]["verdict"] == reference["scorecard"]["verdict"]
    assert mirrored["human_handoff"]["status"] == "pending"
