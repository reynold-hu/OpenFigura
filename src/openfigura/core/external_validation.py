"""Optional external validators for the final evaluation report.

Two external runtimes are supported, both explicit and off by default:

- Khronos glTF-Validator (Apache-2.0): set ``OPENFIGURA_GLTF_VALIDATOR_MODULE``
  to an installed ``gltf-validator`` package directory; Node is found via
  ``OPENFIGURA_NODE`` or PATH.
- trimesh (MIT): set ``OPENFIGURA_TRIMESH_PYTHON`` to a Python with trimesh
  installed.

These run in subprocesses with the caller's environment; missing runtimes are
reported as ``unavailable`` with the reason. Nothing is downloaded, vendored or
executed from the target application.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

BACKENDS = Path(__file__).resolve().parents[1] / "backends"
GLTF_WORKER = BACKENDS / "gltf_validator_worker.mjs"
TRIMESH_WORKER = BACKENDS / "trimesh_check_worker.py"


def _node() -> str | None:
    value = os.environ.get("OPENFIGURA_NODE")
    if value:
        return value if Path(value).is_file() else None
    return shutil.which("node")


def _result(status: str, **fields) -> dict:
    return {"status": status, **fields}


def gltf_validator(model: Path, timeout_s: int = 120) -> dict:
    module = os.environ.get("OPENFIGURA_GLTF_VALIDATOR_MODULE")
    if not module:
        return _result("unavailable", reason="OPENFIGURA_GLTF_VALIDATOR_MODULE is not set")
    module_path = Path(module)
    if not module_path.is_dir():
        return _result("unavailable", reason=f"module directory not found: {module_path}")
    node = _node()
    if node is None:
        return _result("unavailable", reason="node not found (set OPENFIGURA_NODE or PATH)")
    with tempfile.TemporaryDirectory(prefix="openfigura-gltfval-") as folder:
        report_path = Path(folder) / "report.json"
        config_path = Path(folder) / "config.json"
        config_path.write_text(json.dumps({
            "model": str(model), "module": str(module_path.resolve()),
            "report": str(report_path), "max_issues": 1000}), encoding="utf-8")
        argv = [node, str(GLTF_WORKER), str(config_path)]
        started = time.monotonic()
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s,
                                  encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            return _result("unavailable", reason=f"gltf-validator timed out after {timeout_s}s")
        elapsed = round(time.monotonic() - started, 2)
        report = None
        if report_path.is_file():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (ValueError, OSError) as exc:
                return _result("unavailable", reason=f"invalid gltf-validator report: {exc}",
                               command=argv, wall_seconds=elapsed)
    if proc.returncode != 0 or report is None:
        return _result("unavailable", reason=f"gltf-validator worker exited {proc.returncode}",
                       command=argv, wall_seconds=elapsed,
                       stderr_tail=(proc.stderr or "")[-2000:])
    issues = report.get("issues", {})
    return _result("validated", validator=report.get("validator"),
                   validator_version=report.get("validator_version"),
                   issues=issues, command=argv, wall_seconds=elapsed)


def trimesh_check(model: Path, timeout_s: int = 120) -> dict:
    binary = os.environ.get("OPENFIGURA_TRIMESH_PYTHON")
    if not binary:
        return _result("unavailable", reason="OPENFIGURA_TRIMESH_PYTHON is not set")
    if not Path(binary).is_file():
        return _result("unavailable", reason=f"trimesh python not found: {binary}")
    try:
        budget = int(os.environ.get("OPENFIGURA_TRIMESH_MAX_FACES", "300000"))
    except ValueError:
        budget = 300_000
    if budget <= 0:
        budget = 300_000
    try:
        from .inspect import inspect_glb
        triangles = inspect_glb(model)["triangles"]
    except (ValueError, KeyError, IndexError):
        triangles = None
    if triangles is not None and triangles > budget:
        return _result("skipped",
                       reason=f"{triangles} triangles exceeds the trimesh budget "
                              f"({budget}); optimize/retopo first or raise "
                              "OPENFIGURA_TRIMESH_MAX_FACES")
    with tempfile.TemporaryDirectory(prefix="openfigura-trimesh-") as folder:
        report_path = Path(folder) / "report.json"
        config_path = Path(folder) / "config.json"
        config_path.write_text(json.dumps({"model": str(model), "report": str(report_path)}),
                               encoding="utf-8")
        argv = [binary, str(TRIMESH_WORKER), str(config_path)]
        started = time.monotonic()
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s,
                                  encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            return _result("unavailable", reason=f"trimesh check timed out after {timeout_s}s")
        elapsed = round(time.monotonic() - started, 2)
        report = None
        if report_path.is_file():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (ValueError, OSError) as exc:
                return _result("unavailable", reason=f"invalid trimesh report: {exc}",
                               command=argv, wall_seconds=elapsed)
    if proc.returncode != 0 or report is None:
        return _result("unavailable", reason=f"trimesh worker exited {proc.returncode}",
                       command=argv, wall_seconds=elapsed,
                       stderr_tail=(proc.stderr or "")[-2000:])
    return _result("validated", **report, command=argv, wall_seconds=elapsed)
