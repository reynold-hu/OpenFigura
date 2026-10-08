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

    @app.tool(description='Validate and record project pixel dimensions, palette, '
              'outline, shading, FPS and anchor. Does not generate pixels or approve visual quality.')
    def figura_set_style(task_root: str, spec: dict) -> dict:
        return engine.set_style(Task.open(Path(task_root)), spec)

    @app.tool(description='Read latest validated project pixel style or explicit unset status.')
    def figura_project_style(task_root: str) -> dict:
        return engine.project_style(Task.open(Path(task_root)))

    @app.tool(description='Persist a workflow request for later execution. '
              'This foundation API does not start a backend or claim model generation.')
    def figura_workflow_submit(task_root: str, request: dict) -> dict:
        return engine.workflow_submit(Task.open(Path(task_root)), request)

    @app.tool(description='Read persistent stage state and hash-linked asset references.')
    def figura_workflow_status(task_root: str, stage_id: str | None = None) -> dict:
        return engine.workflow_status(Task.open(Path(task_root)), stage_id)

    @app.tool(description='Cancel a queued workflow request; active processes are not killed.')
    def figura_workflow_cancel(task_root: str, stage_id: str) -> dict:
        return engine.workflow_cancel(Task.open(Path(task_root)), stage_id)

    @app.tool(description='Create a fresh attempt after failure or queued cancellation; preserve old evidence.')
    def figura_workflow_resume(task_root: str, stage_id: str) -> dict:
        return engine.workflow_resume(Task.open(Path(task_root)), stage_id)

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

    @app.tool(description="Deterministic input-quality checks (resolution, alpha, "
              "aspect, format). Run BEFORE figura_generate; errors mean generation "
              "would waste a long run. Warnings are advisory.")
    def figura_preflight(image_path: str) -> dict:
        from openfigura.core.preflight import preflight
        return preflight(Path(image_path))

    @app.tool(description="Environment self-check: OS/arch/RAM/disk/GPU probe, "
              "backend availability, and a tiered verdict (ready/capable/blocked). "
              "Run once per machine before first generate.")
    def figura_syscheck() -> dict:
        from openfigura.core.syscheck import check
        return check()

    @app.tool(description="Generate a textured GLB from the staged image. "
              "Runs preflight first and refuses on hard errors unless force=true. "
              "May take tens of minutes on CPU; report wall time honestly.")
    def figura_generate(task_root: str, backend: str = "pixal3d",
                        seed: int | None = None, res: int | None = None,
                        force: bool = False) -> dict:
        params = {k: v for k, v in {"seed": seed, "res": res}.items() if v is not None}
        return engine.generate(Task.open(Path(task_root)), backend, params, force=force)

    @app.tool(description="Native Godot humanoid motion transfer plus Blender IK/contact gate. "
              "Requires skinned GLBs with matching bone names and Mixamo hand chains. "
              "Produces model-animated.glb only after integer-frame regional checks; no full cloth guarantee.")
    def figura_retarget(task_root: str, animation: str, artifact: str = "model-autorig.glb",
                       frames: int = 31, fps: int = 24) -> dict:
        return engine.retarget(Task.open(Path(task_root)),Path(animation),artifact,frames,fps)

    @app.tool(description="External neural humanoid skeleton and skin prediction; no manual coordinates. "
              "Produces a separate static model-autorig.glb/.blend. "
              "MIA runtime/checkpoints required; no motion synthesis or automatic collision repair.")
    def figura_autorig(task_root: str, backend: str = "mia", device: str = "cpu",
                      seed: int = 42, query_chunk: int = 8192, artifact: str = "model.glb") -> dict:
        return engine.autorig(Task.open(Path(task_root)),backend,device,seed,query_chunk,artifact)

    @app.tool(description="Experimental basic-human Rigify binding from explicit bone calibration. "
              "Preserves original and emits model-rigged.glb/.blend. "
              "Automatic skinning fails explicitly; capsule is an opt-in approximate method. "
              "No finger repair or finger chains.")
    def figura_rig(task_root: str, calibration: str,
                   skin_method: str = "automatic", artifact: str = "model.glb") -> dict:
        return engine.rig(Task.open(Path(task_root)), Path(calibration),
                          skin_method=skin_method, artifact=artifact)

    @app.tool(description="Project calibrated RGBA reference pixels onto BaseColor. "
              "Preserves original model; produces model-refined.glb and a trust map. "
              "Does not fix geometry or recover physically correct albedo.")
    def figura_refine_texture(task_root: str, views_dir: str,
                              roi_mask: str | None = None,
                              strength: float = 1.0) -> dict:
        return engine.refine_texture(Task.open(Path(task_root)), Path(views_dir),
                                     Path(roi_mask) if roi_mask else None, strength)

    @app.tool(description="Render neutral multi-view frames (front/side/back/3-4) "
              "with headless Blender. Use facing=180 if the model front points +Y.")
    def figura_render(task_root: str, views: list[str] | None = None,
                      samples: int = 32, facing: int = 0,
                      artifact: str = "model.glb", frame: int = 1) -> dict:
        return engine.render(Task.open(Path(task_root)), views=views,
                             samples=samples, facing_deg=facing, artifact=artifact, frame=frame)

    @app.tool(description="Structural GLB integrity report: meshes, triangles, "
              "attributes, PBR texture references.")
    def figura_inspect(task_root: str, artifact: str = "model.glb") -> dict:
        return engine.inspect(Task.open(Path(task_root)), artifact=artifact)

    @app.tool(description="Export verified artifacts + provenance to a delivery "
              "folder. Refuses if inspection reported problems. format 'glb' is "
              "stdlib; 'fbx'/'obj'/'stl'/'usd' convert the verified snapshot in an "
              "isolated Blender and ship a machine report naming what each format drops.")
    def figura_export(task_root: str, dest: str, format: str = "glb",
                      artifact: str = "model.glb") -> dict:
        return engine.export(Task.open(Path(task_root)), Path(dest), fmt=format, artifact=artifact)

    @app.tool(description="Static mesh operation in an isolated Blender process: "
              "segment | optimize (decimate) | retopo (QuadriFlow) | collision (convex hulls) | uv "
              "(smart project). Preserves the source, emits <stem>-<operation>.glb plus a machine "
              "report. Retopo/UV replace topology or UVs: texture rebake required, no bake here.")
    def figura_mesh(task_root: str, operation: str, params: dict | None = None,
                    artifact: str = "model.glb") -> dict:
        return engine.mesh(Task.open(Path(task_root)), operation, params, artifact=artifact)

    @app.tool(description="Text-to-motion on a rigged GLB via an external generator "
              "(backend 'unimate': UniMate, MIT code but CC BY-NC 4.0 weights — every call "
              "must pass accept_nc_license=True explicitly and the acceptance is ledgered). "
              "The generator never self-certifies: every clip is re-imported and must pass "
              "the same regional contact gate the retarget verb uses; only a gated clip is "
              "delivered as model-motion.glb, all failures are quarantined with reports. "
              "Upstream stops for joint-label/facing review until you pass annotation=.")
    def figura_animate(task_root: str, prompt: str, backend: str = "unimate",
                       repetitions: int = 3, cfg_scale: float = 3.0, seed: int = 42,
                       artifact: str = "model-autorig.glb", annotation: str | None = None,
                       accept_nc_license: bool = False) -> dict:
        return engine.animate(Task.open(Path(task_root)), prompt, backend=backend,
                              repetitions=repetitions, cfg_scale=cfg_scale, seed=seed,
                              artifact=artifact, annotation=annotation,
                              accept_nc_license=accept_nc_license)

    @app.tool(description="Execute one engine verb under a durable workflow stage: "
              "inputs are hash-verified task-local asset references, the verb runs in a private "
              "sandbox, and a pass names the exact output bytes it produced. Identical verified "
              "requests reuse the cached pass without re-running the backend.")
    def figura_execute(task_root: str, step: str, inputs: list[dict],
                       params: dict | None = None) -> dict:
        return engine.execute(Task.open(Path(task_root)), step, inputs, params)

    return app


def main() -> None:
    build().run()


if __name__ == "__main__":
    main()
