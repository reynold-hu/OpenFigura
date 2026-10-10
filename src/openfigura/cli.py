"""OpenFigura CLI: scripts and CI use the same verbs as the MCP server."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from openfigura.core import engine, registry
from openfigura.core import syscheck as _syscheck
from openfigura.core.task import Task


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="openfigura",
                                     description="local 3D asset production for agents")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser('skin-probe',help='fixed bone deformation diagnostics with closeups; not accepted motion')
    p.add_argument('task');p.add_argument('--artifact',default='model.glb');p.add_argument('--config',required=True)
    p.set_defaults(func=lambda a:_print(engine.skin_probe(Task.open(Path(a.task)),
        json.loads(Path(a.config).read_text(encoding='utf-8')),a.artifact)))

    p = sub.add_parser('skin-check',help='read-only weight diagnostics; does not accept deformation or collision quality')
    p.add_argument('task');p.add_argument('--artifact',default='model.glb');p.add_argument('--config',required=True)
    p.set_defaults(func=lambda a:_print(engine.skin_check(Task.open(Path(a.task)),
        json.loads(Path(a.config).read_text(encoding='utf-8')),a.artifact)))

    p = sub.add_parser('pivot',help='rebase a static GLB to ground or centre without re-encoding attributes')
    p.add_argument('task')
    p.add_argument('--mode',choices=['ground','center'],default='ground')
    p.add_argument('--artifact',default='model.glb')
    p.set_defaults(func=lambda a:_print(engine.pivot(Task.open(Path(a.task)),a.mode,a.artifact)))

    p = sub.add_parser('bake', help='high-to-low tangent normal and AO bake in Blender')
    p.add_argument('task')
    p.add_argument('--source', required=True)
    p.add_argument('--artifact', required=True)
    p.add_argument('--resolution', type=int, default=512)
    p.add_argument('--samples', type=int, default=16)
    p.add_argument('--maps', nargs='+', choices=['normal','ao','albedo'], default=['normal','ao'])
    p.add_argument('--cage-extrusion', type=float, default=.01)
    p.add_argument('--ray-distance', type=float, default=.1)
    p.set_defaults(func=lambda a: _print(engine.bake(Task.open(Path(a.task)), a.source, a.artifact,
        {'resolution': a.resolution, 'samples': a.samples, 'maps': a.maps,
         'cage_extrusion': a.cage_extrusion, 'ray_distance': a.ray_distance})))

    p = sub.add_parser('set-style', help='validate and record a project pixel style spec')
    p.add_argument('task')
    p.add_argument('--spec', required=True)
    p.set_defaults(func=lambda a: _print(engine.set_style(
        Task.open(Path(a.task)), json.loads(Path(a.spec).read_text(encoding='utf-8')))))

    p = sub.add_parser('project-style', help='read the latest validated pixel style spec')
    p.add_argument('task')
    p.set_defaults(func=lambda a: _print(engine.project_style(Task.open(Path(a.task)))))

    p = sub.add_parser('workflow-submit', help='persist a stage request; does not execute a backend')
    p.add_argument('task')
    p.add_argument('--spec', required=True)
    p.set_defaults(func=lambda a: _print(engine.workflow_submit(
        Task.open(Path(a.task)), json.loads(Path(a.spec).read_text(encoding='utf-8')))))

    p = sub.add_parser('workflow-status', help='read persistent workflow state')
    p.add_argument('task')
    p.add_argument('--stage', default=None)
    p.set_defaults(func=lambda a: _print(engine.workflow_status(Task.open(Path(a.task)), a.stage)))

    p = sub.add_parser('workflow-cancel', help='cancel a queued stage request')
    p.add_argument('task')
    p.add_argument('stage_id')
    p.set_defaults(func=lambda a: _print(engine.workflow_cancel(Task.open(Path(a.task)), a.stage_id)))

    p = sub.add_parser('workflow-resume', help='create a new attempt from a terminal failed stage')
    p.add_argument('task')
    p.add_argument('stage_id')
    p.set_defaults(func=lambda a: _print(engine.workflow_resume(Task.open(Path(a.task)), a.stage_id)))

    p = sub.add_parser("backends", help="list registered backends and probe status")
    p.set_defaults(func=lambda a: _print({
        bid: {"description": desc, **_probe(bid)}
        for bid, desc in registry.available().items()}))

    p = sub.add_parser("syscheck", help="environment self-check: can this machine generate?")
    p.set_defaults(func=lambda a: _print(_syscheck.check()))

    p = sub.add_parser("new", help="create a task workspace and stage the input image")
    p.add_argument("image")
    p.add_argument("-o", "--out", default="tasks")
    p.add_argument("--name", default=None)
    p.set_defaults(func=_cmd_new)

    p = sub.add_parser("generate", help="image -> textured GLB")
    p.add_argument("task")
    p.add_argument("--backend", default="pixal3d")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--res", type=int, default=None)
    p.add_argument("--force", action="store_true",
                   help="proceed even if preflight reports errors (records the override)")
    p.set_defaults(func=_cmd_generate)

    p = sub.add_parser("retarget", help="native humanoid motion transfer and contact checks")
    p.add_argument("task")
    p.add_argument("--animation", required=True)
    p.add_argument("--artifact", default="model-autorig.glb")
    p.add_argument("--frames", type=int, default=31)
    p.add_argument("--fps", type=int, default=24)
    p.set_defaults(func=lambda a: _print(engine.retarget(Task.open(Path(a.task)),
        Path(a.animation),artifact=a.artifact,frames=a.frames,fps=a.fps)))

    p = sub.add_parser("autorig", help="external neural joint and skin prediction")
    p.add_argument("task")
    p.add_argument("--backend", default="mia")
    p.add_argument("--device", choices=["cpu","cuda"], default="cpu")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--query-chunk", type=int, default=8192)
    p.add_argument("--artifact", default="model.glb")
    p.set_defaults(func=lambda a: _print(engine.autorig(Task.open(Path(a.task)),
        backend=a.backend,device=a.device,seed=a.seed,query_chunk=a.query_chunk,artifact=a.artifact)))

    p = sub.add_parser("transfer-rig", help="copy skeleton + skin weights from a rigged GLB "
                       "onto a matching static GLB of the same character (isolated Blender)")
    p.add_argument("task")
    p.add_argument("--source", required=True, help="rigged source GLB filename in artifacts")
    p.add_argument("--target", default="model.glb", help="static target GLB filename in artifacts")
    p.add_argument("--params", default="{}", help="JSON object: max_influences, refuse_distance_ratio")
    p.set_defaults(func=lambda a: _print(engine.transfer_rig(
        Task.open(Path(a.task)), a.source, artifact=a.target,
        params=json.loads(_json_arg(a.params)))))

    p = sub.add_parser("rig", help="experimental calibrated Rigify binding")
    p.add_argument("task")
    p.add_argument("--calibration", required=True)
    p.add_argument("--skin-method", choices=["automatic", "capsule"], default="automatic")
    p.add_argument("--artifact", default="model.glb")
    p.set_defaults(func=lambda a: _print(engine.rig(Task.open(Path(a.task)),
        Path(a.calibration), skin_method=a.skin_method, artifact=a.artifact)))

    p = sub.add_parser("face-landmarks", help="478-point MediaPipe facial landmarks on the staged "
                       "input image (Apache-2.0 model must be user-fetched; never silent retry)")
    p.add_argument("task")
    p.add_argument("--image", default=None)
    p.set_defaults(func=lambda a: _print(engine.face_landmarks(Task.open(Path(a.task)), image=a.image)))

    p = sub.add_parser("face-mask", help="rasterise face-landmarks.json into an ROI mask PNG "
                       "for refine-texture (suppresses hair/clothing bleed at side seams)")
    p.add_argument("task")
    p.add_argument("--image", default=None)
    p.add_argument("--output", default="face-roi.png")
    p.add_argument("--expand", type=float, default=0.06)
    p.set_defaults(func=lambda a: _print(engine.face_mask(
        Task.open(Path(a.task)), image=a.image, output=a.output, expand=a.expand)))

    p = sub.add_parser("face-expression-report", help="rank MediaPipe ARKit blendshape scores "
                       "from face-landmarks.json into a durable report (no new inference)")
    p.add_argument("task")
    p.add_argument("--image", default=None)
    p.add_argument("--min-score", type=float, default=0.3)
    p.set_defaults(func=lambda a: _print(engine.face_expression_report(
        Task.open(Path(a.task)), image=a.image, min_score=a.min_score)))

    p = sub.add_parser("expression-align", help="register CC0 hm08 face units onto the "
                       "character via render landmarks; acceptance gate must pass")
    p.add_argument("task")
    p.add_argument("--artifact", default="model.glb")
    p.add_argument("--view", default="front")
    p.set_defaults(func=lambda a: _print(engine.expression_align(
        Task.open(Path(a.task)), artifact=a.artifact, view=a.view)))

    p = sub.add_parser("expressions", help="write ARKit-named morph targets onto the character "
                       "from registered CC0 face units, weighted by reference blendshape scores")
    p.add_argument("task")
    p.add_argument("--artifact", default="model.glb")
    p.add_argument("--output", default="model-expressive.glb")
    p.add_argument("--min-score", type=float, default=0.1)
    p.add_argument("--intensity", type=float, default=1.0)
    p.set_defaults(func=lambda a: _print(engine.expressions(
        Task.open(Path(a.task)), artifact=a.artifact, output=a.output,
        min_score=a.min_score, intensity=a.intensity)))

    p = sub.add_parser("head-roi", help="project the model's head band into its calibrated "
                       "generation view; writes an ROI mask PNG for stylized characters "
                       "where landmark detectors find no face")
    p.add_argument("task")
    p.add_argument("--artifact", default="model.glb")
    p.add_argument("--views", default=None, help="calibrated views dir (default: <artifact>.svviews)")
    p.add_argument("--output", default="head-roi.png")
    p.add_argument("--head-fraction", type=float, default=0.18)
    p.add_argument("--expand", type=float, default=0.08)
    p.set_defaults(func=lambda a: _print(engine.head_roi(
        Task.open(Path(a.task)), artifact=a.artifact, views=a.views, output=a.output,
        head_fraction=a.head_fraction, expand=a.expand)))

    p = sub.add_parser("refine-texture", help="project calibrated reference pixels to a new GLB candidate")
    p.add_argument("task")
    p.add_argument("--views-dir", required=True)
    p.add_argument("--roi-mask", default=None)
    p.add_argument("--strength", type=float, default=1.0)
    p.set_defaults(func=lambda a: _print(engine.refine_texture(
        Task.open(Path(a.task)), Path(a.views_dir),
        Path(a.roi_mask) if a.roi_mask else None, a.strength)))

    p = sub.add_parser("preflight", help="input-quality checks, no generation")
    p.add_argument("image")
    from openfigura.core.preflight import preflight as _pf
    p.set_defaults(func=lambda a: _print(_pf(Path(a.image))))

    p = sub.add_parser("render", help="GLB -> neutral multi-view frames")
    p.add_argument("task")
    p.add_argument("--artifact", default="model.glb")
    p.add_argument("--views", nargs="*", default=None)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--frame", type=int, default=1)
    p.add_argument("--facing", type=int, default=0, choices=[0, 90, 180, 270],
                   help="which way the model front points (deg, +Y-left convention)")
    p.set_defaults(func=_cmd_render)

    p = sub.add_parser("inspect", help="GLB structural report")
    p.add_argument("task")
    p.add_argument("--artifact", default="model.glb")
    p.set_defaults(func=lambda a: _print(engine.inspect(Task.open(Path(a.task)), artifact=a.artifact)))

    p = sub.add_parser("animate", help="text-to-motion via an external generator "
                       "(unimate); every clip must pass the regional contact gate before delivery")
    p.add_argument("task")
    p.add_argument("--prompt", required=True)
    p.add_argument("--backend", default="unimate")
    p.add_argument("--repetitions", type=int, default=3)
    p.add_argument("--cfg-scale", type=float, default=3.0)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--artifact", default="model-autorig.glb")
    p.add_argument("--annotation", default=None,
                   help="reviewed joint-label/facing JSON from rig_preprocess")
    p.add_argument("--accept-nc-license", action="store_true",
                   help="opt in to CC BY-NC 4.0 checkpoints for this call (recorded)")
    p.set_defaults(func=lambda a: _print(engine.animate(
        Task.open(Path(a.task)), a.prompt, backend=a.backend, repetitions=a.repetitions,
        cfg_scale=a.cfg_scale, seed=a.seed, artifact=a.artifact, annotation=a.annotation,
        accept_nc_license=a.accept_nc_license)))

    p = sub.add_parser("mesh", help="static mesh op in isolated Blender "
                       "(segment/optimize/retopo/collision/uv)")
    p.add_argument("task")
    p.add_argument("--operation", required=True,
                   choices=["segment", "optimize", "retopo", "collision", "uv"])
    p.add_argument("--params", default="{}", help="JSON object of operation parameters")
    p.add_argument("--artifact", default="model.glb")
    p.set_defaults(func=lambda a: _print(engine.mesh(
        Task.open(Path(a.task)), a.operation, json.loads(_json_arg(a.params)),
        artifact=a.artifact)))

    p = sub.add_parser("execute", help="run one verb under a durable stage record "
                       "with hash-verified inputs and outputs")
    p.add_argument("task")
    p.add_argument("--step", required=True)
    p.add_argument("--inputs", required=True, help="JSON list of asset refs, or @file.json")
    p.add_argument("--params", default="{}", help="JSON object, or @file.json")
    p.set_defaults(func=lambda a: _print(engine.execute(
        Task.open(Path(a.task)), a.step, json.loads(_json_arg(a.inputs)),
        json.loads(_json_arg(a.params)))))

    p = sub.add_parser("export", help="copy verified artifacts to a delivery folder "
                       "(glb via stdlib; fbx/obj/stl/usd convert the verified snapshot in Blender)")
    p.add_argument("task")
    p.add_argument("--artifact", default="model.glb")
    p.add_argument("--dest", required=True)
    p.add_argument("--format", default="glb", choices=["glb", "fbx", "obj", "stl", "usd"])
    p.set_defaults(func=_cmd_export)

    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except (RuntimeError, FileNotFoundError, ValueError) as exc:
        print(f"OPENFIGURA ERROR: {exc}", file=sys.stderr)
        return 1


def _json_arg(value: str) -> str:
    """Accept inline JSON or @path/to/file.json."""
    if value.startswith('@'):
        return Path(value[1:]).read_text(encoding='utf-8')
    return value


def _probe(bid: str) -> dict:
    caps = registry.probe(bid)
    return {"available": caps.available, "hardware": caps.hardware,
            "reason": caps.reason or None, "notes": caps.notes or None}


def _cmd_new(args) -> None:
    task = Task.create(Path(args.out), name=args.name)
    digest = task.stage_input(Path(args.image))
    _print({"task_id": task.id, "root": str(task.root), "input_sha256": digest})


def _cmd_generate(args) -> None:
    params = {k: v for k, v in {"seed": args.seed, "res": args.res}.items() if v is not None}
    _print(engine.generate(Task.open(Path(args.task)), args.backend, params, force=args.force))


def _cmd_render(args) -> None:
    _print(engine.render(Task.open(Path(args.task)), views=args.views,
                         samples=args.samples, facing_deg=args.facing, artifact=args.artifact, frame=args.frame))


def _cmd_export(args) -> None:
    _print(engine.export(Task.open(Path(args.task)), Path(args.dest), fmt=args.format, artifact=args.artifact))


if __name__ == "__main__":
    raise SystemExit(main())
