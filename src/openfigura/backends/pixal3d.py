"""Pixal3D backend: wraps a pixal3d.cpp / trellis-cli style runtime.

The binary is never assumed. It is located via OPENFIGURA_PIXAL_RUNTIME
(explicit path) or `trellis-cli` on PATH, and `capabilities()` reports
exactly what was found — including "not found", which is a valid answer.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from openfigura.backends import base
from openfigura.core import registry
from openfigura.core.registry import Capabilities

DEFAULT_PARAMS = {
    "seed": 42,
    "res": 1024,
    "max_tokens": 8192,
    "atlas": 2048,
    "require_gpu": True,
}


@dataclass
class Pixal3DBackend:
    id = "pixal3d"
    kind = "generate"

    def runtime_path(self) -> Path | None:
        env = os.environ.get("OPENFIGURA_PIXAL_RUNTIME")
        if env:
            p = Path(env)
            return p if p.is_file() else None
        found = base.which("trellis-cli")
        return Path(found) if found else None

    def models_dir(self) -> Path | None:
        env = os.environ.get("OPENFIGURA_PIXAL_MODELS")
        if env:
            p = Path(env)
            return p if p.is_dir() else None
        return None

    def capabilities(self) -> Capabilities:
        runtime = self.runtime_path()
        if runtime is None:
            return Capabilities(False, reason="no runtime: set OPENFIGURA_PIXAL_RUNTIME "
                              "to a pixal3d.cpp binary or put trellis-cli on PATH")
        models = self.models_dir()
        if models is None:
            return Capabilities(False, reason="runtime found but no model dir: "
                              "set OPENFIGURA_PIXAL_MODELS")
        return Capabilities(True, hardware="metal-or-cuda-per-build",
                            notes={"runtime": str(runtime), "models": str(models)})

    def build_command(self, input_png: Path, output_glb: Path,
                      params: dict) -> list[str]:
        runtime = self.runtime_path()
        models = self.models_dir()
        if runtime is None or models is None:
            raise RuntimeError("pixal3d unavailable; run capabilities() first")
        merged = {**DEFAULT_PARAMS, **params}
        argv = [str(runtime), "--sv-image", str(input_png),
                "--output", str(output_glb), "--models", str(models),
                "--seed", str(merged["seed"]), "--res", str(merged["res"]),
                "--max-tokens", str(merged["max_tokens"]),
                "--atlas", str(merged["atlas"]), "--webp", "off"]
        if merged.get("require_gpu"):
            argv.append("--require-gpu")
        return argv

    def generate(self, input_png: Path, output_glb: Path,
                 params: dict | None = None) -> dict:
        """Blocking single-image generation. Returns a ledger dict."""
        argv = self.build_command(Path(input_png), Path(output_glb), params or {})
        timeout = (params or {}).get("timeout_s")
        result = base.run(argv, timeout_s=timeout)
        produced = Path(output_glb).is_file() if result.ok else False
        return {"backend": self.id, **result.ledger(), "artifact": str(output_glb),
                "produced": produced}


registry.register("pixal3d", Pixal3DBackend,
                  "image->textured GLB via pixal3d.cpp runtime (Metal/CUDA)")
