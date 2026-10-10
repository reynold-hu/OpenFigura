# Windows GPU 运行指南：UniMate 与 PartCrafter

日期：2026-10-10。适用：你在一台 NVIDIA GPU 的 Windows 机器上跑 OpenFigura
接不了的生成后端，把产物账本带回 Mac 审计。**诚实边界先说**：UniMate 的
OpenFigura 适配器是按上游源码写的、还没在 Windows 真跑过（第一步就可能磨
合 CLI 参数）；PartCrafter 还没有适配器，本指南给手动配方 + 回收格式。
失败不丢人——账本会精确指出死在哪一步，把日志带回来就是推进。

## 0. 硬件与前提

- NVIDIA GPU：UniMate 采样 ≥8GB 足够；PartCrafter 推理 ≥8GB；SkinTokens
  （以后）≥14GB。驱动支持 CUDA 12.x。
- [Miniconda](https://docs.conda.io/en/latest/miniconda.html)、git、Blender
  （UniMate 驱动网格用它的 CLI；装到 PATH 或记下 blender.exe 路径）。
- 磁盘预留 30GB+（权重不入库，全部现场下载）。

## 1. 工具环境（两个环境分开，别混）

```powershell
# ① OpenFigura 本体（薄 CLI，负责账本与闸）
git clone https://github.com/reynold-hu/OpenFigura.git
cd OpenFigura
conda create -n figura python=3.11 -y
conda activate figura
pip install -e ".[mcp]"

# ② UniMate 运行时（上游钉死 py3.10 + cu124）
cd ..
git clone https://github.com/Friedrich-M/UniMate.git
cd UniMate
git checkout b78c780          # 我们调研钉住的提交
conda create -n unimate python=3.10 -y
conda activate unimate
pip install "setuptools<81"
pip install -r requirements.txt --no-build-isolation
# 权重（注意：CC BY-NC 4.0，非商用；先当评估用）
pip install huggingface_hub
hf download Linzhan/UniMate --repo-type model --local-dir outputs `
  --include "unimate_uniml3d_f60_v3/*.json" --include "unimate_uniml3d_f60_v3/*.npy" `
  --include "unimate_uniml3d_f60_v3/checkpoints/checkpoint_step_150000.pt"
```

把三个路径告诉 OpenFigura（PowerShell 永久化用 `setx`）：

```powershell
$env:OPENFIGURA_UNIMATE_HOME  = "C:\path\to\UniMate"
$env:OPENFIGURA_UNIMATE_PYTHON = "C:\Users\<you>\miniconda3\envs\unimate\python.exe"
$env:OPENFIGURA_UNIMATE_CKPT  = "C:\path\to\UniMate\outputs\unimate_uniml3d_f60_v3"
```

验收：`openfigura backends` 里 `unimate` 应报 `available: True`（False 时
reason 会写明缺哪个：runtime/ckpt/CUDA 探测）。

## 2. UniMate：跑通一条动作

```powershell
conda activate figura
# 任务目录从 Mac 拷来，或现场新建（需要已绑骨的 GLB：MIA 产物 model-autorig.glb）
openfigura new <参考图.png> -o tasks --name win-motion
copy <绑好骨的模型.glb> tasks\win-motion\artifacts\model-autorig.glb
openfigura animate tasks\win-motion --prompt "An object walks forward." `
  --repetitions 3 --accept-nc-license
```

流程与拦截点（每一步失败都会记账，不会假装成功）：
1. **rig_preprocess 停审**：上游默认在关节标注后停下要求人工复核
   `annotation.json` / `REVIEW.md`。看完加 `--annotation <文件>` 重跑。
   我们的预检会先拒重复骨名/超 71 关节/无蒙皮的模型——这是特性。
2. **采样**：`unimate.inference.sample`，60 帧 @30fps × N reps。
3. **驱动**：`scripts/run_animate_motion.sh`（需要 blender 在 PATH；
   Git Bash 或改 .sh 为 .ps1 等价命令——第一台机器上大概率要磨）。
4. **接触闸**：每条 clip 重新导入过 OpenFigura 的区域接触检查，
   **只有全帧干净的才交付** `model-motion.glb`，其余隔离进
   `artifacts/rejected/`。

预期摩擦（我们按源码写的命令行，第一次跑真机可能要微调）：
Windows 下 `.sh` 包装、路径分隔符、`--formats glb,fbx` 逗号解析。
**别手改产物绕过账本**——改适配器源码，失败也要失败在台账里。

## 3. PartCrafter：手动配方（无适配器）

```powershell
git clone https://github.com/wgsxm/PartCrafter.git   # MIT
conda create -n partcrafter python=3.10 -y
conda activate partcrafter
# 按上游 README 装依赖与权重（TripoSG 底座，数 GB）
```

跑一个整模的部件分解（参数名以上游 README 为准）：

```powershell
python demo.py --input <整模.glb> --output <outdir> --num_parts 8 --seed 42
```

**回收格式（重要，我按这个接）**：

```
partcrafter-out/<角色名>/
  part_0.glb ... part_N.glb
  meta.json     # {"tool":"partcrafter","commit":"<git rev-parse HEAD>",
                #  "input_sha256":"<整模sha256>","num_parts":N,"seed":42,
                #  "gpu":"<nvidia-smi 名字>","wall_seconds":...,
                #  "command":"<完整命令行>"}
```

拿到 Mac 后我写 `partcrafter` 适配器时直接按这个契约 ingest，账本补齐。

## 4. 带回来的东西（zip 或 git 新分支都行）

1. 整个任务目录（`provenance.json`、`stages/`、`artifacts/`、`motion/`、日志）
2. `partcrafter-out/`（含 meta.json）
3. 两个环境的 `pip freeze` + `nvidia-smi` 输出
4. 失败也没关系：**失败日志就是产物**

## 5. 许可红线（别越）

- UniMate 权重 **CC BY-NC 4.0**：评估可以，商用产出物不行，除非另行授权。
  `--accept-nc-license` 会把你的逐次确认写进账本。
- PartCrafter 代码 MIT；它微调的 TripoSG 底座权重有自己的许可，
  下载时逐个看一眼 LICENSE 并抄进 meta.json。
- 参考图/角色素材**不需要也不应该**上传到任何云服务；这套流程全本地。

## 6. 已知未验证清单（跑之前心里有数）

- [ ] 适配器里 rig_preprocess/sample/drive 的确切参数拼写
- [ ] Windows 下 `bash scripts/run_animate_motion.sh` 的可用性
- [ ] MIA 骨架（52 关节、mixamorig 命名、可能有重名叶骨）过上游预检的实际表现
- [ ] 采样显存实测占用（文档未给出）

第一条真实运行日志比十页计划值钱。跑完把目录带回来，哪怕全红。
