"""Engine tests with a fake backend; no external binaries required."""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openfigura.core import registry  # noqa: E402
from openfigura.core.engine import export, generate, inspect  # noqa: E402
from openfigura.core.task import Task  # noqa: E402


def make_minimal_glb(path: Path) -> None:
    gltf = {
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1,
                                                   "TEXCOORD_0": 2},
                                    "indices": 0, "material": 0,
                                    "mode": 4}]}],
        "materials": [{"pbrMetallicRoughness": {}}],
        "accessors": [{"count": 6}],
        "buffers": [{"byteLength": 12}],
    }
    payload = json.dumps(gltf).encode()
    payload += b" " * (-len(payload) % 4)
    binchunk = b"\x00" * 12
    total = 12 + 8 + len(payload) + 8 + len(binchunk)
    path.write_bytes(
        struct.pack("<III", 0x46546C67, 2, total)
        + struct.pack("<II", len(payload), 0x4E4F534A) + payload
        + struct.pack("<II", len(binchunk), 0x004E4942) + binchunk)


class FakeBackend:
    id = "fake"
    kind = "generate"

    def __init__(self, fail=False):
        self.fail = fail

    def capabilities(self):
        from openfigura.core.registry import Capabilities
        return Capabilities(not self.fail, hardware="cpu", reason="fake" if self.fail else "")

    def generate(self, input_png, output_glb, params):
        if self.fail:
            return {"backend": self.id, "command": "fake", "exit_code": 1,
                    "wall_seconds": 0.0, "stderr_tail": "boom", "produced": False}
        make_minimal_glb(Path(output_glb))
        return {"backend": self.id, "command": "fake", "exit_code": 0,
                "wall_seconds": 0.0, "stderr_tail": "", "produced": True}


class FakeMatteBackend(FakeBackend):
    """Generation backend that needs a matte step first, like pixal3d."""

    id = "fake-matte"

    def __init__(self):
        super().__init__()
        self.seen_input = None
        self.fail_prepare = False

    def prepare_input(self, input_png, output_glb, params):
        cutout = Path(output_glb).with_name("matte_cutout.png")
        if self.fail_prepare:
            return {"backend": self.id, "output": str(cutout), "produced": False,
                    "command": "fake matte", "exit_code": 1,
                    "wall_seconds": 0.0, "stderr_tail": "no model"}
        cutout.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        return {"backend": self.id, "output": str(cutout), "produced": True,
                "command": "fake matte", "exit_code": 0,
                "wall_seconds": 0.0, "stderr_tail": ""}

    def generate(self, input_png, output_glb, params):
        self.seen_input = Path(input_png)
        return super().generate(input_png, output_glb, params)


registry.register("fake", lambda: FakeBackend(), "test backend")
registry.register("fake-fail", lambda: FakeBackend(fail=True), "failing test backend")
_MATTE_BACKEND = FakeMatteBackend()
registry.register("fake-matte", lambda: _MATTE_BACKEND, "test matte backend")


def _png_bytes(w: int = 1024, h: int = 1200) -> bytes:
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr
            + struct.pack(">I", 0) + b"IEND" + struct.pack(">I", 0))


def _task(tmp_path: Path) -> Task:
    task = Task.create(tmp_path / "tasks", name="t1")
    img = tmp_path / "ref.png"
    img.write_bytes(_png_bytes())
    task.stage_input(img)
    return task


def test_generate_inspect_export(tmp_path):
    task = _task(tmp_path)
    ledger = generate(task, "fake", {"seed": 1})
    assert ledger["status"] == "pass"
    assert task.artifact("model.glb").is_file()
    report = inspect(task)
    assert report["ok"], report["problems"]
    assert report["meshes"] == 1 and report["materials_with_pbr"] == 1
    manifest = export(task, tmp_path / "dist")
    assert (tmp_path / "dist" / "t1.glb").is_file()
    assert manifest["glb_sha256"]


def test_generate_failure_is_recorded(tmp_path):
    task = _task(tmp_path)
    try:
        generate(task, "fake-fail")
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "unavailable" in str(exc) or "exited" in str(exc)
    steps = [e["step"] for e in Task.open(task.root).entries]
    assert "input" in steps


def test_generate_runs_preprocess_and_records_it(tmp_path):
    _MATTE_BACKEND.seen_input = None
    _MATTE_BACKEND.fail_prepare = False
    task = _task(tmp_path)
    ledger = generate(task, "fake-matte")
    assert ledger["status"] == "pass"
    assert _MATTE_BACKEND.seen_input.name == "matte_cutout.png"
    entries = Task.open(task.root).entries
    prep = next(e for e in entries if e["step"] == "preprocess")
    assert prep["status"] == "pass"
    assert prep["input_sha256"] and prep["output_sha256"]
    gen = next(e for e in entries if e["step"] == "generate")
    assert gen["input_sha256"] == prep["output_sha256"]


def test_generate_records_failed_preprocess(tmp_path):
    _MATTE_BACKEND.fail_prepare = True
    try:
        task = _task(tmp_path)
        try:
            generate(task, "fake-matte")
            assert False, "expected RuntimeError"
        except RuntimeError as exc:
            assert "preprocessing" in str(exc)
        prep = next(e for e in Task.open(task.root).entries if e["step"] == "preprocess")
        assert prep["status"] == "fail"
    finally:
        _MATTE_BACKEND.fail_prepare = False


def test_export_refuses_broken_glb(tmp_path):
    task = _task(tmp_path)
    generate(task, "fake")
    bad = task.artifact("model.glb")
    raw = bad.read_bytes()
    gltf = json.loads(raw[20:20 + struct.unpack_from("<I", raw, 12)[0]])
    gltf["meshes"][0]["primitives"][0]["attributes"].pop("NORMAL")
    make_minimal_glb_from(bad, gltf)
    report = inspect(task)
    assert not report["ok"]
    try:
        export(task, tmp_path / "dist")
        assert False, "expected refusal"
    except RuntimeError as exc:
        assert "NORMAL" in str(exc)


def make_minimal_glb_from(path: Path, gltf: dict) -> None:
    payload = json.dumps(gltf).encode()
    payload += b" " * (-len(payload) % 4)
    binchunk = b"\x00" * 12
    total = 12 + 8 + len(payload) + 8 + len(binchunk)
    path.write_bytes(
        struct.pack("<III", 0x46546C67, 2, total)
        + struct.pack("<II", len(payload), 0x4E4F534A) + payload
        + struct.pack("<II", len(binchunk), 0x004E4942) + binchunk)


def test_cli_backends_lists_registered(tmp_path, capsys):
    from openfigura.cli import main
    assert main(["backends"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert "fake" in out and "pixal3d" in out and "blender" in out
