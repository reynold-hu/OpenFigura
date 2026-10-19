"""MCP server smoke test: spawn the stdio server and list its tools."""
from __future__ import annotations

import importlib.util
import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(importlib.util.find_spec("mcp") is None,
                                reason="MCP extra not installed")


def _send(proc: subprocess.Popen, payload: dict) -> None:
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()


def _pump(stream, sink: queue.Queue) -> None:
    for line in stream:
        sink.put(line)
    sink.put(None)


def _read(proc: subprocess.Popen, timeout: float = 30.0) -> dict:
    # A reader thread works on Windows too; selectors cannot select on pipes
    # there (the POSIX-only version of this test timed out on the RTX 4060 box).
    lines = proc._smoke_lines
    try:
        line = lines.get(timeout=timeout)
    except queue.Empty:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        stderr = proc.stderr.read() if proc.stderr else ""
        raise AssertionError(f"MCP server did not reply in {timeout}s: {stderr[-1000:]}")
    assert line is not None, "MCP server closed stdout"
    return json.loads(line)


@pytest.fixture
def server():
    env = {**os.environ,
           "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    proc = subprocess.Popen(
        [sys.executable, "-m", "openfigura.mcp_server"],
        cwd=Path(__file__).resolve().parents[1], env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", bufsize=1)
    lines: queue.Queue = queue.Queue()
    threading.Thread(target=_pump, args=(proc.stdout, lines), daemon=True).start()
    proc._smoke_lines = lines
    try:
        yield proc
    finally:
        if proc.stdin:
            proc.stdin.close()
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_server_initializes_and_lists_all_tools(server):
    _send(server, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                   "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                              "clientInfo": {"name": "pytest-smoke", "version": "0"}}})
    init = _read(server)
    assert init["id"] == 1 and "result" in init
    assert init["result"]["serverInfo"]["name"]

    _send(server, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    _send(server, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    listed = _read(server)
    tools = {tool["name"]: tool for tool in listed["result"]["tools"]}
    assert len(tools) >= 34
    assert {"figura_generate", "figura_evaluate", "figura_score",
            "figura_print_check", "figura_inspect", "figura_export"} <= set(tools)
    assert tools["figura_generate"]["inputSchema"]["properties"]["dry_run"]["default"] is False
