"""External validator plumbing without requiring Node or trimesh."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openfigura.core import external_validation  # noqa: E402
from test_printability import TETRA, write_glb  # noqa: E402


def test_runtimes_are_unavailable_when_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENFIGURA_GLTF_VALIDATOR_MODULE", raising=False)
    path = write_glb(tmp_path / "tetra.glb", [TETRA])
    result = external_validation.gltf_validator(path)
    assert result["status"] == "unavailable"
    assert "OPENFIGURA_GLTF_VALIDATOR_MODULE" in result["reason"]

    monkeypatch.delenv("OPENFIGURA_TRIMESH_PYTHON", raising=False)
    result = external_validation.trimesh_check(path)
    assert result["status"] == "unavailable"
    assert "OPENFIGURA_TRIMESH_PYTHON" in result["reason"]


def test_trimesh_skips_over_the_face_budget(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENFIGURA_TRIMESH_PYTHON", sys.executable)
    monkeypatch.setenv("OPENFIGURA_TRIMESH_MAX_FACES", "1")
    path = write_glb(tmp_path / "tetra.glb", [TETRA])
    result = external_validation.trimesh_check(path)
    assert result["status"] == "skipped"
    assert "exceeds the trimesh budget" in result["reason"]


def test_trimesh_rejects_missing_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENFIGURA_TRIMESH_PYTHON", "/nonexistent/python")
    path = write_glb(tmp_path / "tetra.glb", [TETRA])
    result = external_validation.trimesh_check(path)
    assert result["status"] == "unavailable"
    assert "not found" in result["reason"]
