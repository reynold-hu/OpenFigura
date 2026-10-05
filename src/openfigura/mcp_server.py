"""OpenFigura MCP server (stdio): the same engine verbs as MCP tools.

Run with `openfigura-mcp` and register in any MCP-capable client, e.g.
opencode's opencode.json:

    {"mcp": {"openfigura": {"type": "local",
      "command": [".venv/bin/openfigura-mcp"], "enabled": true}}}

Generation is intentionally NOT awaited inside a single tool call for long
runs: `figura_generate` blocks (backends report their own wall time), and
clients are expected to run it with generous timeouts. Progress streaming is
a v0.2 item.
"""
from __future__ import annotations

from pathlib import Path

from openfigura.core import engine, registry
from openfigura.core.task import Task


def build():
    try:
        from mcp.server.mcpserver import MCPServer as _Server  # mcp >= 2
    except ImportError:
        try:
            from mcp.server.fastmcp import FastMCP as _Server  # mcp 1.x
        except ImportError as exc:
            raise SystemExit(
                "MCP extra not installed: pip install 'openfigura[mcp]'") from exc

    app = _Server("openfigura")

    @app.tool(description="List generation/render backends and probe availability.")
    def figura_backends() -> dict:
        out = {}
        for bid, desc in registry.available().items():
            caps = registry.probe(bid)
            out[bid] = {"description": desc, "available": caps.available,
                        "hardware": caps.hardware, "reason": caps.reason or None}
        return out

    @app.tool(description="Create a task workspace and stage a reference image.")
    def figura_new_task(image_path: str, out_dir: str = "tasks",
                        name: str | None = None) -> dict:
        task = Task.create(Path(out_dir), name=name)
        digest = task.stage_input(Path(image_path))
        return {"task_root": str(task.root), "task_id": task.id, "input_sha256": digest}

    @app.tool(description="Generate a textured GLB from the staged image. "
              "May take tens of minutes on CPU; report wall time honestly.")
    def figura_generate(task_root: str, backend: str = "pixal3d",
                        seed: int | None = None, res: int | None = None) -> dict:
        params = {k: v for k, v in {"seed": seed, "res": res}.items() if v is not None}
        return engine.generate(Task.open(Path(task_root)), backend, params)

    @app.tool(description="Render neutral multi-view frames (front/side/back/3-4) "
              "with headless Blender. Use facing=180 if the model front points +Y.")
    def figura_render(task_root: str, views: list[str] | None = None,
                      samples: int = 32, facing: int = 0) -> dict:
        return engine.render(Task.open(Path(task_root)), views=views,
                             samples=samples, facing_deg=facing)

    @app.tool(description="Structural GLB integrity report: meshes, triangles, "
              "attributes, PBR texture references.")
    def figura_inspect(task_root: str) -> dict:
        return engine.inspect(Task.open(Path(task_root)))

    @app.tool(description="Export verified artifacts + provenance to a delivery "
              "folder. Refuses if inspection reported problems.")
    def figura_export(task_root: str, dest: str, format: str = "glb") -> dict:
        return engine.export(Task.open(Path(task_root)), Path(dest), fmt=format)

    return app


def main() -> None:
    build().run()


if __name__ == "__main__":
    main()
