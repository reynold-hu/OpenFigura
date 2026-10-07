"""Pixal3D adapter tests: discovery, command construction, honest probes.
No runtime binary is required; env vars point at temp fakes.
"""
from __future__ import annotations

import os
import struct
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


def _png(path: Path, color_type: int) -> None:
    """Header-only PNG good enough for the stdlib header checks."""
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
                     + struct.pack(">IIBBBBB", 64, 64, 8, color_type, 0, 0, 0)
                     + struct.pack(">I", 0) + b"IEND" + struct.pack(">I", 0))


def test_matte_command_shape(tmp_path):
    md, old = _backend_with_env(tmp_path)
    try:
        (md / "birefnet.gguf").write_bytes(b"fake")
        b = Pixal3DBackend()
        argv = b.build_matte_command(tmp_path / "in.png", tmp_path / "matte.glb", {})
        assert argv[1:] == [str(tmp_path / "in.png"), str(tmp_path / "matte.glb"),
                            "--models", str(md), "--bg-removal", "birefnet",
                            "--bg-only", "--require-gpu"]
        assert b.matte_mode() == "birefnet"
    finally:
        _restore(old)


def test_matte_mode_falls_back_to_threshold(tmp_path):
    md, old = _backend_with_env(tmp_path)
    try:
        b = Pixal3DBackend()
        assert b.matte_mode() == "threshold"
        argv = b.build_matte_command(tmp_path / "in.png", tmp_path / "matte.glb", {})
        assert "threshold" in argv
    finally:
        _restore(old)


def test_prepare_input_mattes_only_when_needed(tmp_path):
    md, old = _backend_with_env(tmp_path)
    try:
        rt = tmp_path / "trellis-cli"
        rt.write_text('#!/bin/sh\nprintf x > "${2%.glb}_cutout.png"\nexit 0\n')
        rt.chmod(0o755)
        b = Pixal3DBackend()
        raw = tmp_path / "raw.png"
        _png(raw, color_type=2)
        prep = b.prepare_input(raw, tmp_path / "matte.glb", {})
        assert prep is not None and prep["produced"]
        assert Path(prep["output"]).name == "matte_cutout.png"
        assert (tmp_path / "matte_cutout.png").is_file()
        alpha = tmp_path / "alpha.png"
        _png(alpha, color_type=6)
        assert b.prepare_input(alpha, tmp_path / "matte2.glb", {}) is None
        assert b.prepare_input(raw, tmp_path / "matte3.glb", {"matte": "off"}) is None
    finally:
        _restore(old)
