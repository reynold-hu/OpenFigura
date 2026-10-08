"""Task workspace: one directory per asset production run.

Layout (everything relative, so a task folder can be moved or zipped):

    <task-id>/
        input/            reference image copy + sha256
        model.glb         generated asset (or artifacts/<name>)
        render/           neutral multi-view frames
        inspect.json      structural report
        provenance.json   the ledger: commands, hashes, timings
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contracts import AssetRef
from .style import StyleSpec


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class Task:
    root: Path
    id: str
    created_utc: float
    entries: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def create(cls, out_dir: Path, name: str | None = None) -> "Task":
        task_id = name or time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
        root = Path(out_dir) / task_id
        (root / "input").mkdir(parents=True, exist_ok=True)
        (root / "render").mkdir(parents=True, exist_ok=True)
        (root / "artifacts").mkdir(parents=True, exist_ok=True)
        task = cls(root=root, id=task_id, created_utc=time.time())
        task._flush()
        return task

    @classmethod
    def open(cls, root: Path) -> "Task":
        root = Path(root)
        data = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
        task = cls(root=root, id=data["task_id"], created_utc=data["created_utc"],
                   entries=data["entries"])
        return task

    def stage_input(self, path: Path) -> str:
        """Copy the reference image into the task and hash it."""
        src = Path(path)
        if not src.is_file():
            raise FileNotFoundError(src)
        dest = self.root / "input" / src.name
        shutil.copy2(src, dest)
        digest = sha256_file(dest)
        self.record("input", {"file": f"input/{src.name}", "sha256": digest,
                              "source": str(src)})
        return digest

    def record(self, step: str, data: dict[str, Any]) -> None:
        self.entries.append({"step": step, "utc": time.time(), **data})
        self._flush()

    def record_style(self, spec: StyleSpec) -> None:
        """Record declared style requirements, without a quality verdict."""
        if not isinstance(spec, StyleSpec):
            raise TypeError('spec must be a StyleSpec')
        self.record('style', {'style_spec': spec.to_dict()})

    def record_asset(self, ref: AssetRef) -> None:
        """Only append an asset whose task-local bytes match its reference."""
        if not isinstance(ref, AssetRef):
            raise TypeError('ref must be an AssetRef')
        ref.verify(self.root)
        self.record('asset', {'asset': ref.to_dict()})

    def artifact(self, name: str) -> Path:
        return self.root / "artifacts" / name

    def _flush(self) -> None:
        payload = {
            "task_id": self.id,
            "created_utc": self.created_utc,
            "openfigura_version": __import__("openfigura").__version__,
            "entries": self.entries,
        }
        (self.root / "provenance.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
