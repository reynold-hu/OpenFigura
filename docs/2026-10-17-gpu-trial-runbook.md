# GPU trial runbook: TripoSG / TripoSF / Hi3DGen on Windows

Purpose: run the three open, MIT-licensed geometry pipelines on the user's
Windows NVIDIA box (RTX 4060 class) and bring back comparable evidence. This
is a **measurement plan**, not a promise that every model fits. OpenFigura
stays CPU-first; these trials only decide whether an optional GPU backend is
worth registering.

Reference: `docs/2026-10-16-generation-mechanism-survey.md` for the mechanism
and weight sizes. Do not upload user art to any hosted service during the
trials; everything below runs locally.

## 0. Host reality (verify first)

```bat
nvidia-smi
```
Record GPU name, total VRAM, driver and CUDA version. The three targets differ:

| Target | Weights | Documented requirement | 8 GB expectation |
|---|---|---|---|
| TripoSG | transformer 5.76 GB fp32 + VAE 0.97 GB | ≥8 GB (README) | **borderline but plausible**: inference casts to fp16 (~2.9 GB) + activations |
| Hi3DGen | ss/slat flows + decoders ≈ 2.7 GB fp16 + DINOv2-L | CUDA only, no stated VRAM | **plausible**; spconv/xformers wheels are the real risk |
| TripoSF | SparseFlex VAE (size not listed) | ≥12 GB for 1024³ | **likely OOM**; treat a failure as a valid result |

Use ASCII-only paths (`C:\openfigura\...`). The repo already records that
non-ASCII paths (e.g. `桌面`) break some Windows runners.

## 1. Common setup

- Install a CUDA-enabled PyTorch matching the driver (2.4 for Hi3DGen/TripoSG;
  TripoSF also expects 2.x), in a dedicated venv or conda env per model.
- Keep every command's stdout/stderr, `nvidia-smi --query-gpu=memory.used`
  snapshots, wall time, and output hashes.
- Use one shared input image from the repo, e.g.
  `golden/cases/head-sculpt/input.png` (copy it to the Windows box).

## 2. TripoSG (image → SDF latent → mesh)

```bat
git clone https://github.com/VAST-AI-Research/TripoSG
cd TripoSG
conda create -n triposg python=3.10 -y && conda activate triposg
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
python -m scripts.inference_triposg --image-input C:\openfigura\input.png ^
  --output-path C:\openfigura\triposg.glb --num-inference-steps 50 --guidance-scale 7
```

The script defaults: 50 steps, CFG 7, fp16 on CUDA, optional `--faces` for
pymeshlab decimation, optional RMBG background removal. Record: output GLB
sha256, peak VRAM, wall time, any OOM and the exact command.

## 3. Hi3DGen (normal bridging: BiRefNet → normal → TRELLIS flows)

```bat
git clone --recursive https://github.com/ByteDance/Hi3DGen
cd Hi3DGen
conda create -n hi3dgen python=3.10 -y && conda activate hi3dgen
pip install torch==2.4.0 torchvision==0.19.0 --index-url https://download.pytorch.org/whl/cu121
pip install spconv-cu121==2.3.6 xformers==0.0.27.post2
pip install -r requirements.txt
python app.py
```

Open the local Gradio page and run the shared input. The app downloads
`Stable-X/trellis-normal-v0-1`, `Stable-X/yoso-normal-v1-8-1` and
`ZhengPeng7/BiRefNet` into `weights/`. Bring back: the generated mesh, the
normal map used, peak VRAM, wall time, and whether spconv/xformers imported
cleanly (that is the Windows risk).

## 4. TripoSF (SparseFlex VAE reconstruction; not a generator)

```bat
git clone https://github.com/VAST-AI-Research/TripoSF
cd TripoSF
conda create -n triposf python=3.10 -y && conda activate triposf
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
python inference.py --mesh-path C:\openfigura\bunny.glb ^
  --output-dir C:\openfigura\triposf-out --config configs/TripoSFVAE_1024.yaml
```

This is a VAE: it reconstructs a watertight sparse-isosurface mesh at 1024³
from an input mesh. The 8 GB expectation is **OOM**; record it if so. If a
lower-resolution or fp16 config exists in the repo, use it and record the
deviation. The useful question is whether a 4060-class card can produce a
watertight 1024³ result at all.

## 5. Evidence to bring back

For each run, a folder with: command line, stdout/stderr, `nvidia-smi` peak,
wall time, input sha256, output file + sha256, and 1–2 neutral renders. If a
run is impossible (OOM, wheel failure), a short log of the failure is as
valuable as a success. Do not commit weights or outputs to the repo; keep
them under a local `C:\openfigura\runs\...` folder.

## 6. What OpenFigura does with the results

- If TripoSG fits: candidate optional backend behind an env var, never a
  default; capability notes record weights, dtype, VRAM and steps.
- If Hi3DGen fits: geometry-only backend with normal-map evidence; the
  normal image and inverse normalization must be ledgered.
- TripoSF is a **post-process** candidate (watertight conversion) feeding
  `print-check`, not a replacement for generation.
- Any integration stays CPU-first: missing GPU must remain `unavailable`
  with a reason, never a crash or a fake success.
