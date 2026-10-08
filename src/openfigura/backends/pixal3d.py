"""Pixal3D backend: wraps a pixal3d.cpp / trellis-cli style runtime.

The binary is never assumed. It is located via OPENFIGURA_PIXAL_RUNTIME
(explicit path) or `trellis-cli` on PATH, and `capabilities()` reports
exactly what was found — including "not found", which is a valid answer.

Cross-platform: the runtime ships per-OS builds (Metal on macOS, CUDA on
Windows/Linux) behind one CLI, so this adapter stays OS-agnostic and only
reports the platform it runs on. The SV flow refuses inputs without a real
alpha matte, so `prepare_input` runs the runtime's own background removal
(BiRefNet when `birefnet.gguf` is present, threshold otherwise) as the first
pipeline step instead of wasting a long generation on a refusal.
"""
from __future__ import annotations

import os
import json
import platform as _platform
import sys
from dataclasses import dataclass
from pathlib import Path

from openfigura.backends import base
from openfigura.core import registry
from openfigura.core.preflight import read_image_info
from openfigura.core.registry import Capabilities

DEFAULT_PARAMS = {
    "seed": 42,
    "res": 1024,
    "max_tokens": 8192,
    "atlas": 2048,
    "require_gpu": True,
}

MATTE_MODEL = "birefnet.gguf"   # optional; threshold mode is the fallback


@dataclass
class Pixal3DBackend:
    id = "pixal3d"
    kind = "generate"

    def profile(self) -> dict:
        path = Path(os.environ.get('OPENFIGURA_PIXAL_PROFILE',
                    str(Path.home() / '.config/openfigura/pixal3d.json')))
        if not path.is_file():
            return {}
        try:
            config = json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, OSError) as exc:
            raise ValueError('invalid Pixal3D profile') from exc
        if (not isinstance(config, dict) or set(config) != {'schema_version','runtime','models'}
                or type(config['schema_version']) is not int or config['schema_version'] != 1
                or any(not isinstance(config[k], str) or not Path(config[k]).is_absolute()
                       for k in ('runtime','models'))):
            raise ValueError('invalid Pixal3D profile schema or absolute paths')
        return config

    def runtime_path(self) -> Path | None:
        if 'OPENFIGURA_PIXAL_RUNTIME' in os.environ:
            value = os.environ['OPENFIGURA_PIXAL_RUNTIME']
            if not value:
                return None
            p = Path(value)
            return p if p.is_file() else None
        found = base.which("trellis-cli")
        if found:
            return Path(found)
        value = self.profile().get('runtime')
        return Path(value) if value and Path(value).is_file() else None

    def models_dir(self) -> Path | None:
        if 'OPENFIGURA_PIXAL_MODELS' in os.environ:
            value = os.environ['OPENFIGURA_PIXAL_MODELS']
            if not value:
                return None
            p = Path(value)
            return p if p.is_dir() else None
        value = self.profile().get('models')
        return Path(value) if value and Path(value).is_dir() else None

    def matte_mode(self) -> str:
        """Preferred background-removal mode for this install."""
        models = self.models_dir()
        if models is not None and (models / MATTE_MODEL).is_file():
            return "birefnet"
        return "threshold"

    def capabilities(self) -> Capabilities:
        try:
            runtime = self.runtime_path()
            models = self.models_dir()
        except ValueError as exc:
            return Capabilities(False, reason=str(exc))
        if runtime is None:
            return Capabilities(False, reason="no runtime: set OPENFIGURA_PIXAL_RUNTIME "
                              "to a pixal3d.cpp binary or put trellis-cli on PATH")
        if models is None:
            return Capabilities(False, reason="runtime found but no model dir: "
                              "set OPENFIGURA_PIXAL_MODELS")
        return Capabilities(True, hardware="metal-or-cuda-per-build",
                            notes={"runtime": str(runtime), "models": str(models),
                                   "platform": f"{sys.platform}-{_platform.machine()}",
                                   "matte": self.matte_mode()})

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

    def build_matte_command(self, input_image: Path, output_glb: Path,
                            params: dict) -> list[str]:
        runtime = self.runtime_path()
        models = self.models_dir()
        if runtime is None or models is None:
            raise RuntimeError("pixal3d unavailable; run capabilities() first")
        merged = {**DEFAULT_PARAMS, **params}
        argv = [str(runtime), str(input_image), str(output_glb),
                "--models", str(models), "--bg-removal", self.matte_mode(),
                "--bg-only"]
        if merged.get("require_gpu"):
            argv.append("--require-gpu")
        return argv

    def prepare_input(self, input_image: Path, output_glb: Path,
                      params: dict | None = None) -> dict | None:
        """Auto-matte an input that lacks a real alpha matte.

        Returns None when nothing is needed (input already has alpha, or the
        caller passed matte="off"). Otherwise runs `<runtime> <in> <out.glb>
        --bg-only`, which writes `<out stem>_cutout.png` next to output_glb;
        that cutout becomes the generation input.
        """
        params = params or {}
        if params.get("matte", "auto") == "off":
            return None
        info = read_image_info(Path(input_image))
        if info and info.get("has_alpha"):
            return None
        output_glb = Path(output_glb)
        argv = self.build_matte_command(Path(input_image), output_glb, params)
        result = base.run(argv, timeout_s=params.get("timeout_s"))
        cutout = output_glb.with_name(output_glb.stem + "_cutout.png")
        return {"backend": self.id, "output": str(cutout),
                "produced": bool(result.ok and cutout.is_file()),
                **result.ledger()}

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
