"""trimesh geometry audit worker (optional external runtime).

Reads a config JSON path as the last argument and writes a JSON report.
Geometry checks only; no rendering, no repairs, no network.
"""
import json
import sys
from pathlib import Path

import numpy as np
import trimesh

cfg = json.loads(Path(sys.argv[-1]).read_text(encoding="utf-8"))
mesh = trimesh.load(cfg["model"], force="mesh", process=True)
if isinstance(mesh, trimesh.Scene):
    mesh = trimesh.util.concatenate(tuple(mesh.geometry.values()))
vertices_before_weld = int(len(mesh.vertices))
# Topology checks use exact-position welding, matching OpenFigura's printability:
# glTF splits vertices for normal/UV seams, which would otherwise report false
# boundaries and components. Texture/normal attributes are not used here.
mesh.merge_vertices(merge_tex=True, merge_norm=True)
mesh.remove_unreferenced_vertices()
nondegenerate = mesh.nondegenerate_faces()
degenerate = int(len(mesh.faces) - int(np.count_nonzero(nondegenerate)))
report = {
    "trimesh_version": trimesh.__version__,
    "vertices": int(len(mesh.vertices)),
    "vertices_before_weld": vertices_before_weld,
    "welded": True,
    "faces": int(len(mesh.faces)),
    "degenerate_faces": degenerate,
    "is_watertight": bool(mesh.is_watertight),
    "is_winding_consistent": bool(mesh.is_winding_consistent),
    "is_volume": bool(mesh.is_volume),
    "components": len(mesh.split(only_watertight=False)),
    "euler_number": int(mesh.euler_number),
    "area_m2": round(float(mesh.area), 9),
    "extents_m": [round(float(v), 9) for v in mesh.extents],
}
try:
    report["volume_m3"] = round(float(mesh.volume), 12)
except Exception as exc:  # noqa: BLE001 - non-volume meshes are explicit
    report["volume_m3"] = None
    report["volume_reason"] = str(exc)
Path(cfg["report"]).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print("TRIMESH_DONE", flush=True)
