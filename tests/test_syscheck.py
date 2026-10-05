"""syscheck structure tests: values are machine-dependent, contract is not."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openfigura.core.syscheck import check  # noqa: E402


def test_report_contract():
    r = check()
    assert r["verdict"] in {"ready", "capable", "blocked"}
    assert isinstance(r["problems"], list) and isinstance(r["cautions"], list)
    assert r["os"] and r["arch"] and r["python"]
    assert set(r["backends"]) >= {"pixal3d", "blender"}
    assert "memory_hard_gb" in r["floors"]
    # blocked iff problems exist; verdict must match its own evidence
    assert (r["verdict"] == "blocked") == bool(r["problems"])


def test_memory_probe_returns_sane_number():
    from openfigura.core.syscheck import _memory_bytes
    mem = _memory_bytes()
    assert mem is None or 1e9 <= mem <= 1e12
