"""Blender backend: neutral multi-view rendering of a generated GLB.

Headless `blender -b --factory-startup` with an embedded script — the same
pattern proven in the tarotist-xiaoman v4 pipeline. Lighting is deliberately
neutral: quality claims must survive plain studio lights, not beautification.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from openfigura.backends import base
from openfigura.core import registry
from openfigura.core.registry import Capabilities

VIEWS = {  # name: view direction (camera sits at center + dir * distance)
    "front": (0.0, -1.0, 0.0),
    "three-quarter": (0.62, -0.78, 0.35),
    "side": (1.0, 0.0, 0.0),
    "back": (0.0, 1.0, 0.0),
}

_SCRIPT = '''
import bpy, json, math, sys
from mathutils import Vector, Matrix
cfg = json.loads(open(sys.argv[-1], encoding="utf-8").read())
rot = math.radians(cfg.get("facing_deg", 0))
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete()
bpy.ops.import_scene.gltf(filepath=cfg["glb"])
deps = bpy.context.evaluated_depsgraph_get()
mins = Vector((1e9, 1e9, 1e9)); maxs = Vector((-1e9, -1e9, -1e9)); found = False
for obj in bpy.context.scene.objects:
    if obj.type != 'MESH':
        continue
    ev = obj.evaluated_get(deps)
    for c in ev.bound_box:
        w = ev.matrix_world @ Vector(c)
        mins = Vector(map(min, mins, w)); maxs = Vector(map(max, maxs, w))
        found = True
if not found:
    raise RuntimeError("no mesh objects after import")
size = maxs - mins; center = (maxs + mins) / 2
maxdim = max(size.x, size.y, size.z, 1e-4)
scene = bpy.context.scene
scene.render.engine = 'CYCLES'; scene.cycles.samples = cfg["samples"]
scene.cycles.use_denoising = True
world = bpy.data.worlds.get('World') or bpy.data.worlds.new('World')
scene.world = world; world.use_nodes = True
bg = world.node_tree.nodes['Background']
bg.inputs['Color'].default_value = (.85, .85, .85, 1); bg.inputs['Strength'].default_value = .55
def aim(o, t): o.rotation_euler = (Vector(t) - o.location).to_track_quat('-Z','Y').to_euler()
for nm, off, pw, sz in [('Key',(-3,-4,5),420,4), ('Fill',(3,-2,3),240,3), ('Rim',(1,3,4),360,3)]:
    d = bpy.data.lights.new(nm,'AREA'); d.energy = pw * maxdim * maxdim; d.size = sz * maxdim
    o = bpy.data.objects.new(nm,d); scene.collection.objects.link(o)
    o.location = center + Vector(off) * maxdim * 1.5; aim(o, center)
camd = bpy.data.cameras.new('Cam'); cam = bpy.data.objects.new('Cam', camd)
scene.collection.objects.link(cam); scene.camera = cam; camd.type = 'ORTHO'
for view, direction in cfg["views"].items():
    dirv = Vector(direction); dirv.rotate(Matrix.Rotation(rot, 3, 'Z'))
    dirv.normalize()
    cam.location = center + dirv * maxdim * 4
    aim(cam, center)
    horiz = size.x if abs(dirv.y) > abs(dirv.x) else size.y
    if view == "three-quarter": horiz = max(size.x, size.y)
    camd.ortho_scale = max(horiz, size.z / 1.25) * 1.35
    scene.render.resolution_x = 720; scene.render.resolution_y = 900
    scene.render.filepath = cfg["out_dir"] + '/' + view + '.png'
    bpy.ops.render.render(write_still=True)
print("OPENFIGURA_RENDER_DONE")
'''


@dataclass
class BlenderBackend:
    id = "blender"
    kind = "render"

    def binary(self) -> str | None:
        return base.which("blender") or (
            "/Applications/Blender.app/Contents/MacOS/Blender"
            if Path("/Applications/Blender.app").exists() else None)

    def capabilities(self) -> Capabilities:
        b = self.binary()
        if b is None:
            return Capabilities(False, reason="blender not found on PATH or /Applications")
        return Capabilities(True, hardware="cpu-or-metal", notes={"binary": b})

    def render_views(self, glb: Path, out_dir: Path, views: list[str] | None = None,
                     samples: int = 32, facing_deg: int = 0) -> dict:
        binary = self.binary()
        if binary is None:
            raise RuntimeError("blender unavailable; run capabilities() first")
        out_dir.mkdir(parents=True, exist_ok=True)
        chosen = {k: VIEWS[k] for k in (views or VIEWS)}
        cfg = {"glb": str(Path(glb).resolve()), "out_dir": str(Path(out_dir).resolve()),
               "samples": samples, "facing_deg": facing_deg,
               "views": {k: list(v) for k, v in chosen.items()}}
        cfg_path = None
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(cfg, f)
            cfg_path = f.name
        start = time.monotonic()
        proc = subprocess.run([binary, "-b", "--factory-startup", "--python-expr",
                               _SCRIPT, "--", cfg_path],
                              capture_output=True, text=True, timeout=3600)
        result = base.CommandResult(argv=[binary, "-b", "--factory-startup",
                                          "--python-expr", "<render script>"],
                                    exit_code=proc.returncode,
                                    wall_seconds=round(time.monotonic() - start, 2),
                                    stdout_tail=(proc.stdout or "")[-4000:],
                                    stderr_tail=(proc.stderr or "")[-4000:])
        Path(cfg_path).unlink(missing_ok=True)
        frames = sorted(p.name for p in Path(out_dir).glob("*.png"))
        return {"backend": self.id, **result.ledger(), "frames": frames}


registry.register("blender", BlenderBackend, "neutral multi-view Cycles renders via headless Blender")
