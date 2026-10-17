"""pymeshlab shape-diameter worker: run under an external Python with pymeshlab.

Reads a config JSON path as the last argument (Blender-worker convention) and
writes a JSON report. Values are in mesh units (glTF meters for these assets);
the caller converts to millimetres. This is a thickness *proxy*, not a
calibrated wall-thickness measurement.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pymeshlab

cfg = json.loads(Path(sys.argv[-1]).read_text(encoding="utf-8"))
meshset = pymeshlab.MeshSet()
meshset.load_new_mesh(cfg["model"])
meshset.apply_filter("compute_scalar_by_shape_diameter_function_per_vertex")
values = np.array([float(v) for v in meshset.current_mesh().vertex_scalar_array()])
if values.size == 0:
    raise ValueError("shape diameter produced no vertex scalars")
finite = values[np.isfinite(values)]
if finite.size == 0:
    raise ValueError("all shape-diameter samples are non-finite")
report = {
    "method": "pymeshlab compute_scalar_by_shape_diameter_function_per_vertex",
    "proxy": "shape diameter function per vertex; not a calibrated wall thickness",
    "vertices": int(values.size),
    "finite_samples": int(finite.size),
    "nonfinite_samples": int(values.size - finite.size),
    "min_m": float(finite.min()),
    "p5_m": float(np.percentile(finite, 5)),
    "p10_m": float(np.percentile(finite, 10)),
    "median_m": float(np.median(finite)),
}
Path(cfg["report"]).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print("THICKNESS_DONE", flush=True)
