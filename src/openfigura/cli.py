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

    p = sub.add_parser("rig", help="experimental calibrated Rigify binding")
    p.add_argument("task")
    p.add_argument("--calibration", required=True)
    p.add_argument("--skin-method", choices=["automatic", "capsule"], default="automatic")
    p.add_argument("--artifact", default="model.glb")
    p.set_defaults(func=lambda a: _print(engine.rig(Task.open(Path(a.task)),
        Path(a.calibration), skin_method=a.skin_method, artifact=a.artifact)))

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

    p = sub.add_parser("export", help="copy verified artifacts to a delivery folder")
    p.add_argument("task")
    p.add_argument("--artifact", default="model.glb")
    p.add_argument("--dest", required=True)
    p.add_argument("--format", default="glb", choices=["glb"])
    p.set_defaults(func=_cmd_export)

    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except (RuntimeError, FileNotFoundError, ValueError) as exc:
        print(f"OPENFIGURA ERROR: {exc}", file=sys.stderr)
        return 1


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
