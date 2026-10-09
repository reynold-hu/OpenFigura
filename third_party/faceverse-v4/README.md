# FaceVerse V4 source import

Upstream: https://github.com/LizhenWangT/FaceVerse_v4
Commit: `19c67cc4d7234b1ea7d55a185a2cb55fd49bb877`.

All 28 checkout files (excluding Git administration) were copied and verified
before subtraction. Retained source under `src/openfigura/_vendor/faceverse_v4/`
keeps upstream MIT licenses, including the 3DDFA_V2 and Deep3DFaceRecon notices.
The root OpenFigura AGPL license does not relabel this third-party source.

Retained: face geometry/network modules, Sim3DR CPU source and license/docs.
Moved to local archive: webcam controller, examples, placeholder model directory
and the precompiled Windows Python3.9 extension. Restore from the original clone
or the exact relative paths in `.local/runs/2026-10-09-face-code-import/removed/`.

Only source patch: remove the eager network import from `faceversev4/__init__.py`.
Geometry remains upstream; network can still be imported explicitly with its
optional dependencies. SOURCE.json records every retained file's hashes.

No model weights are included. Their authorization must be checked separately
before default distribution or commercial asset generation. No neural inference
or face-quality pass is claimed. CPU smoke runs original rotation/eye/projection/
normal functions with synthetic tensors. Sim3DR has not been compiled.
