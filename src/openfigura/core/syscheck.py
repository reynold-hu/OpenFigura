"""Environment self-check: can this machine actually run generation?

Stdlib-only hardware probe with honest tiering:
  ready     - backends found, memory/disk in recommended range
  capable   - everything needed exists, but resources are tight
  blocked   - something required is missing (says WHAT, verbatim)

GPU/VRAM detection is best-effort (nvidia-smi / system_profiler); when we
cannot see a GPU we say "not detected", never "none".
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys


def _memory_bytes() -> int | None:
    if sys.platform == "darwin":
        try:
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"],
                                          text=True, timeout=10)
            return int(out.strip())
        except Exception:
            return None
    try:
        pages = int(subprocess.check_output(
            ["getconf", "_PHYS_PAGES"], text=True).strip())
        size = int(subprocess.check_output(
            ["getconf", "PAGESIZE"], text=True).strip())
        return pages * size
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong),
                            ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return stat.ullTotalPhys
        except Exception:
            pass
    return None


def _gpus() -> list[dict]:
    gpus = []
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name,memory.total",
                 "--format=csv,noheader,nounits"], text=True, timeout=10)
            for line in out.strip().splitlines():
                name, mem = line.split(",", 1)
                gpus.append({"vendor": "nvidia", "name": name.strip(),
                             "vram_mb": int(mem.strip())})
        except Exception:
            gpus.append({"vendor": "nvidia", "name": "nvidia-smi present but query failed"})
    if sys.platform == "darwin":
        try:
            out = subprocess.check_output(
                ["system_profiler", "SPDisplaysDataType", "-json"],
                text=True, timeout=30)
            import json
            for dev in json.loads(out).get("SPDisplaysDataType", []):
                gpus.append({"vendor": "apple", "name": dev.get("sppci_model", "Apple GPU"),
                             "note": "unified memory shared with system"})
        except Exception:
            pass
    return gpus


def check() -> dict:
    """Full environment report + tiered verdict against documented floors."""
    mem = _memory_bytes()
    mem_gb = round(mem / 1e9, 1) if mem else None
    disk = shutil.disk_usage("/")
    disk_gb = round(disk.free / 1e9, 1)
    os_name, machine = platform.system(), platform.machine()

    from openfigura.core import registry
    backends = {}
    for bid, desc in registry.available().items():
        caps = registry.probe(bid)
        backends[bid] = {"available": caps.available, "reason": caps.reason or None}

    problems, cautions = [], []
    gen = backends.get("pixal3d", {})
    if not gen.get("available"):
        problems.append("no generation backend available: "
                        + (gen.get("reason") or "register one or set env vars"))
    if not backends.get("blender", {}).get("available"):
        cautions.append("blender missing: generate works, but render/inspect "
                        "quality gate cannot run (export stays allowed)")
    if mem_gb is not None and mem_gb < 8:
        problems.append(f"{mem_gb} GB RAM below the 8 GB hard floor")
    elif mem_gb is not None and mem_gb < 16:
        cautions.append(f"{mem_gb} GB RAM: verified path is 16 GB (M5); expect "
                        "lower res or longer runs; never kill a run to fake success")
    if disk_gb < 12:
        problems.append(f"{disk_gb} GB free disk < 12 GB floor (weights ~8 GB + outputs)")
    elif disk_gb < 30:
        cautions.append(f"{disk_gb} GB free disk: tight for weights plus task history")

    tier = "blocked" if problems else ("capable" if cautions else "ready")
    return {
        "os": f"{os_name} {platform.release()}", "arch": machine,
        "python": platform.python_version(),
        "memory_gb": mem_gb, "disk_free_gb": disk_gb,
        "gpus": _gpus() or "none detected (may exist undetected)",
        "backends": backends,
        "verdict": tier, "problems": problems, "cautions": cautions,
        "floors": {"memory_hard_gb": 8, "memory_recommended_gb": 16,
                   "disk_free_hard_gb": 12, "disk_free_recommended_gb": 30,
                   "source": "docs/testing-guide.md; verified host: Apple M5/16GB, 27m15s at res 1024"},
    }
