"""MCP server smoke test: spawn the stdio server and list its tools."""
from __future__ import annotations

import importlib.util
import json
import os
import selectors
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(importlib.util.find_spec("mcp") is None,
                                reason="MCP extra not installed")


def _send(proc: subprocess.Popen, payload: dict) -> None:
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()


def _read(proc: subprocess.Popen, timeout: float = 30.0) -> dict:
    assert proc.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    try:
        if not selector.select(timeout):
            stderr = proc.stderr.read() if proc.stderr else ""
            raise AssertionError(f"MCP server did not reply in {timeout}s: {stderr[-1000:]}")
        line = proc.stdout.readline()
    finally:
        selector.close()
    assert line, "MCP server closed stdout"
    return json.loads(line)


@pytest.fixture
def server():
    env = {**os.environ,
           "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    proc = subprocess.Popen(
        [sys.executable, "-m", "openfigura.mcp_server"],
        cwd=Path(__file__).resolve().parents[1], env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1)
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
