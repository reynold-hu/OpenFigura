"""Optional CPU wall-thickness proxy via an external pymeshlab runtime.

The project venv stays stdlib-only. Set ``OPENFIGURA_PYMESHLAB_PYTHON`` to a
Python interpreter with pymeshlab (and numpy) installed; print-check then runs
the worker in a subprocess and records its command, exit code and wall time.
Unset or broken runtimes are reported as ``unavailable`` with the reason, never
guessed. The metric is a shape-diameter-function proxy, not a calibrated wall
thickness.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

ENV_VAR = "OPENFIGURA_PYMESHLAB_PYTHON"
WORKER = Path(__file__).resolve().parents[1] / "backends" / "pymeshlab_thickness_worker.py"


def runtime() -> str | None:
    value = os.environ.get(ENV_VAR)
    if not value:
        return None
    path = Path(value)
    return str(path) if path.is_file() else None


def measure(model: Path, timeout_s: int = 600) -> dict:
    binary = runtime()
    if binary is None:
        return {"status": "unavailable",
                "reason": f"{ENV_VAR} is not set to an existing Python with pymeshlab"}
    with tempfile.TemporaryDirectory(prefix="openfigura-thickness-") as folder:
        report_path = Path(folder) / "report.json"
        config_path = Path(folder) / "config.json"
        config_path.write_text(json.dumps({"model": str(model), "report": str(report_path)}),
                               encoding="utf-8")
        argv = [binary, str(WORKER), str(config_path)]
        started = time.monotonic()
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s)
        ledger = {"command": argv, "exit_code": proc.returncode,
                  "wall_seconds": round(time.monotonic() - started, 2),
                  "stderr_tail": (proc.stderr or "")[-2000:]}
        report = None
        if report_path.is_file():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (ValueError, OSError) as exc:
                ledger["stderr_tail"] += f"\nInvalid thickness report: {exc}"
    if proc.returncode != 0 or report is None:
        return {"status": "unavailable",
                "reason": f"pymeshlab worker exited {proc.returncode}",
                "command": argv, "wall_seconds": ledger["wall_seconds"],
                "stderr_tail": ledger["stderr_tail"]}
    return {
        "status": "measured",
        "method": report.get("method"),
        "proxy": report.get("proxy"),
        "vertices": report.get("vertices"),
        "finite_samples": report.get("finite_samples"),
        "nonfinite_samples": report.get("nonfinite_samples"),
        "min_mm": round(float(report["min_m"]) * 1000.0, 4),
        "p5_mm": round(float(report["p5_m"]) * 1000.0, 4),
        "p10_mm": round(float(report["p10_m"]) * 1000.0, 4),
        "median_mm": round(float(report["median_m"]) * 1000.0, 4),
        **ledger,
    }
