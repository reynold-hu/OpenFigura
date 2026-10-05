"""Pixal3D adapter tests: discovery, command construction, honest probes.
No runtime binary is required; env vars point at temp fakes.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openfigura.backends.pixal3d import Pixal3DBackend  # noqa: E402


def _backend_with_env(tmp_path, runtime=True, models=True):
    rt = None
    if runtime:
        rt = tmp_path / "trellis-cli"
        rt.write_text("#!/bin/sh\nexit 0\n")
        rt.chmod(0o755)
    md = tmp_path / "models-sv"
    if models:
        md.mkdir()
    old = dict(os.environ)
    os.environ["OPENFIGURA_PIXAL_RUNTIME"] = str(rt) if rt else ""
    os.environ["OPENFIGURA_PIXAL_MODELS"] = str(md) if md.is_dir() else ""
    return md, old


def _restore(old):
    os.environ.pop("OPENFIGURA_PIXAL_RUNTIME", None)
    os.environ.pop("OPENFIGURA_PIXAL_MODELS", None)
    os.environ.update(old)


def test_capabilities_report_missing_runtime(tmp_path):
    old = dict(os.environ)
    os.environ["OPENFIGURA_PIXAL_RUNTIME"] = str(tmp_path / "nope")
    os.environ.pop("OPENFIGURA_PIXAL_MODELS", None)
    try:
        caps = Pixal3DBackend().capabilities()
        assert not caps.available and "runtime" in caps.reason
    finally:
        _restore(old)


def test_capabilities_report_missing_models(tmp_path):
    md, old = _backend_with_env(tmp_path, runtime=True, models=False)
    try:
        caps = Pixal3DBackend().capabilities()
        assert not caps.available and "model dir" in caps.reason
    finally:
        _restore(old)


def test_command_matches_verified_invocation(tmp_path):
    md, old = _backend_with_env(tmp_path)
    try:
        b = Pixal3DBackend()
        assert b.capabilities().available
        argv = b.build_command(tmp_path / "in.png", tmp_path / "out.glb", {"seed": 42})
        joined = " ".join(argv)
        # The shape proven in the tarotist-xiaoman 2026-10-05 run:
        assert argv[1:] == ["--sv-image", str(tmp_path / "in.png"),
                           "--output", str(tmp_path / "out.glb"),
                           "--models", str(md),
                           "--seed", "42", "--res", "1024",
                           "--max-tokens", "8192", "--atlas", "2048",
                           "--webp", "off", "--require-gpu"]
        assert "--require-gpu" in joined
    finally:
        _restore(old)


def test_params_override_defaults(tmp_path):
    md, old = _backend_with_env(tmp_path)
    try:
        b = Pixal3DBackend()
        argv = b.build_command(tmp_path / "in.png", tmp_path / "out.glb",
                               {"res": 512, "require_gpu": False, "seed": 7})
        assert "512" in argv and "7" in argv and "--require-gpu" not in argv
    finally:
        _restore(old)
