"""Compat pre-script for the UniMate drive-step Blender (passed via --python
BEFORE animate_motion.py; Blender executes --python scripts in order).

cond.npy and the sampled motion .npy files are pickled dicts written by
numpy>=2 in the sampling environment, so their pickles reference
``numpy._core.*`` module paths. The Blender minor pinned by upstream (4.0.x)
ships numpy 1.x, which only knows ``numpy.core`` — unpickling raises
ModuleNotFoundError: No module named 'numpy._core' (first RTX 4060 run,
2026-10-11, drive job). Aliasing the whole numpy.core submodule tree under
its numpy._core name makes the files load unchanged. Deliberately NOT done
by upgrading Blender's numpy: bpy is compiled against the bundled 1.x ABI.
"""
import importlib
import pkgutil
import sys

import numpy as np

if not hasattr(np, '_core'):
    import numpy.core as _core

    np._core = _core
    sys.modules['numpy._core'] = _core
    for module in pkgutil.walk_packages(_core.__path__, prefix='numpy.core.'):
        try:
            loaded = importlib.import_module(module.name)
        except Exception:  # noqa: BLE001 — optional/private submodules vary
            continue
        alias = 'numpy._core' + module.name[len('numpy.core'):]
        sys.modules.setdefault(alias, loaded)
