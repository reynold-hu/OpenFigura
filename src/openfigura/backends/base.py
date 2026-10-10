"""Shared subprocess plumbing for CLI-wrapped backends."""
from __future__ import annotations

import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CommandResult:
    argv: list[str]
    exit_code: int
    wall_seconds: float
    stdout_tail: str
    stderr_tail: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    @property
    def command_line(self) -> str:
        return shlex.join(self.argv)

    def ledger(self) -> dict:
        return {"command": self.command_line, "exit_code": self.exit_code,
                "wall_seconds": self.wall_seconds, "stderr_tail": self.stderr_tail}


def which(tool: str) -> str | None:
    return shutil.which(tool)


def run(argv: list[str], timeout_s: float | None = None,
        cwd: Path | None = None) -> CommandResult:
    start = time.monotonic()
    # Explicit UTF-8 with replacement: Windows would otherwise decode child
    # output through the locale codec (cp1252) and crash on UTF-8 box glyphs
    # and progress bars emitted by external runtimes (first RTX 4060 run,
    # 2026-10-11, masked the sampler's real stderr).
    proc = subprocess.run(argv, cwd=cwd, timeout=timeout_s,
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    wall = time.monotonic() - start
    return CommandResult(
        argv=list(argv), exit_code=proc.returncode, wall_seconds=round(wall, 2),
        stdout_tail=(proc.stdout or "")[-4000:], stderr_tail=(proc.stderr or "")[-4000:],
    )
