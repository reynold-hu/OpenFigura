# 生成机理调研：Tripo / Hi3D(Sparc3D) / Meshy / Hi3DGen — 2026-10-16

> **定位**：OpenFigura 是独立开源项目（AGPL-3.0），目标是本地、可复算的
> 3D 资产工具链；本文只整理**公开论文、公开代码与公开权重**中的生成机理，
> 用于评估哪些开源部件值得自研接入。我们不复制、不复刻商业产品，也不使用
> 其未公开实现。

产品面之后，本文专攻**模型生成机理**：每家到底用什么表示、什么生成器、
什么条件、多少分辨率、推理配置、代码与权重是否可得。**没有跑过任何模型**；
结论来自论文正文、官方仓库配置/源码、公开权重文件结构与负向检索，
逐条标注证据级别（`[论文]`/`[代码]`/`[权重]`/`[厂]`/`[推]`/`[无]`）。

证据目录：`.local/runs/2026-10-16-meshy-hi3d-review/algorithms/`
（论文文本、README、模型配置、专利查询结果，sha256 见文末）。

---

## 0. 一句话结论

- 商业侧（Tripo P2.0/Nexus、Hi3D Sparc3D、Meshy T2）与开源侧
  （TRELLIS.2、TripoSG、TripoSF、Hi3DGen）**已经收敛到同一条技术路线**：
  **稀疏体素/隐式场潜变量 + 流匹配/扩散生成 + 高分辨率等值面提取**。
  差别在"表示"（SLAT / SDF / Sparcubes / SparseFlex）与"条件"（图像 /
  法线 / 多视图）。
- **能拿到的代码与权重全在 Tripo 开源线与 Hi3DGen**（均 MIT）；
  **Sparc3D 只有论文，代码被 Math Magic 闸门；Meshy 没有论文、没有专利**。
- 对 OpenFigura 最直接可用的两块：**TripoSF 的 SparseFlex VAE（水密
  1024³ 重建，MIT 权重）** 与 **TripoSG（1.5B SDF rectified-flow，MIT）**；
  二者都是 CUDA 路线，和 MIA/UniMate 共用一台 NVIDIA 机器即可验证。
  我们的 pixal3d 后端本身就属于 TRELLIS.2 家族，这条升级路径是同源的。

---

## 1. 证据与边界

- 论文：Sparc3D arXiv 2505.14521 全文（`sparc3d-paper.txt`，41k 字符），
  TripoSG 2502.06608、TripoSF 2503.21732、TripoSR 2403.02151 摘要。
- 代码/配置：TripoSR `config.yaml`；TripoSG `model_index.json` +
  `transformer/config.json` + `vae/config.json` + rectified-flow scheduler +
  `scripts/inference_triposg.py`；TripoSF `configs/TripoSFVAE_1024.yaml` +
  `pipeline.json`；Hi3DGen 本地仓库源码 + `Stable-X/trellis-normal-v0-1`
  的 `pipeline.json`。
- 权重结构：HF 文件树与大小（下载量、safetensors 字节数）。
- 负向检索：Google Patents assignee 查询 `Meshy` / `Meshy LLC` / `VAST AI`
  / `Tripo` → 0 条；`Math Magic` → 1 条（CN121437712A，**2D 卡通角色
  特征映射**，与 3D 生成机理无关）。
- 边界：没有 CUDA 机器，**所有模型都未运行**；参数来自配置与论文，
  实际显存/速度以各家 README 与论文表为准，且可能随版本变化。

---

## 2. 生态谱系（谁和谁同源）

```
TRELLIS (Microsoft, 2024)  ── SLAT: 稀疏体素 + 结构化潜变量 + 流匹配
   │                         └─ 开源 MIT；我们的 pixal3d 后端 = TRELLIS.2 运行时
   ├─ Hi3DGen (ByteDance/CUHK, ICCV'25, MIT)
   │     法线桥接：TRELLIS 架构 + normal-conditioned flow
   ├─ Sparc3D (NTU + Math Magic, 论文；代码 gated)
   │     TRELLIS latent flow 微调到 Sparconv-VAE 潜空间 + Sparcubes 提取
   ├─ TripoSG (VAST/Tripo, MIT)   SDF-VAE + rectified-flow DiT（自研 VAE）
   └─ TripoSF (VAST/Tripo, MIT)   SparseFlex VAE（1024³ 稀疏等值面）

TripoSR (VAST + Stability, MIT)  ── LRM 路线（triplane NeRF），与上面不同代
```

判断依据：Sparc3D 论文自述"fine-tune the TRELLIS latent flow model"；
Hi3DGen 的权重仓库直接叫 `trellis-normal-v0-1` 且 pipeline 类为
`TrellisImageTo3DPipeline`；TripoSF 论文/仓库承认 builds upon TRELLIS +
FlexiCubes；TripoSG 论文对比 TRELLIS 并自研 SDF-VAE。

---

## 3. Tripo 系的机理（全部开源可查）

### 3.1 TripoSR（第一代，feedforward）

`[代码]` `config.yaml` 实测：DINOv2 ViT-B/16 编码图像 → **triplane
32×32×1024** token → 16 层 1D transformer（16 heads×64, cross 768）→
triplane 上采样到 40 通道 → **NeRF MLP**（120→64，9 层 SiLU，128 samples/ray）
→ 体渲染训练，推理时 marching cubes 出网格。`<0.5s / A100，约 6GB VRAM`
`[论文]`。本质是 LRM（Large Reconstruction Model）的工程强化版，
不是稀疏体素路线。

### 3.2 TripoSG（当前开源主力，SDF + rectified flow）

`[代码]` 结构：
- **SDF-VAE**：`Tripo2VAEModel`，frequency 位置编码（freq=8），输入 3 通道，
  潜变量 64 通道；encoder 8 层/宽 512、decoder 16 层/宽 1024（8 heads）。
- **生成器**：`TripoSGDiTModel`，width 2048、21 层、16 heads、
  cross-attention 1024（DINOv2 图像特征），输入 64 通道潜变量。
- **采样**：`RectifiedFlowScheduler`（1000 训练步，shift=1）；
  推理默认 **50 步、CFG 7.0**（`scripts/inference_triposg.py`）。
- **训练数据/监督** `[论文]`：200 万 image–SDF 对；SDF loss + 法线引导 +
  **eikonal loss** 的混合监督；1.5B 参数、2048 latent tokens。
- 出网格后可选 pymeshlab 二次减面（`--faces`）。
- 权重：`transformer` safetensors **5.76 GB**（1.5B fp32）+ VAE 0.97 GB；
  README 要求 **≥8GB VRAM**。

机理含义：图像条件 → 64ch SDF 潜空间整流流 → 解码 SDF → 等值面。
比 TripoSR 的 triplane NeRF 表达力强、几何更锐利，且潜空间是 3D 的
（不是 2D 监督），代价是 token 数（2048）与显存。

### 3.3 TripoSF（高分辨率任意拓扑表示，SparseFlex VAE）

`[代码]` `TripoSFVAE_1024.yaml` 实测：
- 输入：**点云 + 法线**（`sample_points_num: 819,200`）。
- **local PointNet**（LocalPoolPointnet，6→1024，5 blocks）逐点特征 →
  **稀疏 3D 编解码器**：12 blocks、768 通道、latent 8 通道、
  **Swin attention**（window 8）、12 heads。
- 输出：**SparseFlex**（FlexiCubes 的稀疏版）参数，支持 **256→1024³**
  重建（模型名 `pretrained_TripoSFVAE_256i1024o`），`pruning` 开关针对
  开放表面。`[论文]`：frustum-aware sectional voxel training，
  只激活视锥相关体素，支持从渲染损失端到端训练到 1024³；
  **≥12GB VRAM**。
- 仓库**只发布 VAE**（重建），生成模型未放出 `[代码]`。

机理含义：它解决的是"表示"而非"生成"——把任意拓扑（含开放面）的网格
变成 1024³ 稀疏可微等值面，**天然水密/可打印**。Tripo 产品里
"高精度/干净拓扑/Smart Mesh" 很可能建立在这条表示线上 `[推]`。

### 3.4 Tripo 商业模型（P2.0/Nexus、v3.1）

`[无]` 无论文、无公开权重、无相关专利。从产品参数与开源线推断：
- P2.0 "quad-dominant + 原生部件" 大概率是 TripoSG/SF 之上再训练的
  topology-aware 生成器或部件级生成 `[推]`；
- Smart Mesh 的 5k/20k/50k 面数档与 TripoSF 的 1024³ 表示、TripoSG 的
  `--faces` 后处理在能力上吻合 `[推]`。
**证据强度不够，只能作为路线参考，不能作为复现依据。**

---

## 4. Hi3D（hi3d.ai / Math Magic）— Sparc3D

`[论文]` arXiv 2505.14521 全文实测（`sparc3d-paper.txt`）：

### 4.1 表示：Sparcubes（稀疏可变形 marching cubes）

步骤（论文 §3）：① 在网格表面窄带提取**活跃稀疏体素**（角点距表面 < ε）；
② 对活跃体素做 **flood-fill 得到粗符号标签**；③ 以**梯度下降优化网格顶点
的形变**（deformation field），并用**视角相关的 2D 渲染损失**精修（可微）；
④ 输出**水密 1024³** 表面。自己实现 **CUDA kernel**；论文称
**<30 秒**完成水密化，比此前方法快 3×，且保留小部件与内部结构。
位姿/符号的粗到细估计 + 可变形修正是它和 FlexiCubes/SparseFlex 的关键差异。

### 4.2 编码：Sparconv-VAE

- **全稀疏卷积 encoder + self-pruning decoder**（解码时只保留必要的稀疏
  体素），**不用全局注意力**；目标是"模态一致"——输入的稀疏 SDF/
  形变场和输出的稀疏场同构，避免 TRELLIS 式 2D 监督 VAE 的分辨率损失与
  内部几何错误（论文明确把"开放表面/内部结构/打印"当动机）。
- 训练：**50 万 Objaverse/Objaverse-XL 资产**，32×A100、batch 32、
  AdamW lr 1e-4、**2 天**。

### 4.3 生成：TRELLIS latent flow 微调

- 把 **TRELLIS 的 latent flow 模型**在 Sparconv-VAE 的潜空间上微调：
  64×A100、batch 64、**10 天**。
- 推理：**CFG 3.5、25 步**（与 TRELLIS 一致）。
- 因此 hi3d.ai 的完整链条 = 图像条件 → （TRELLIS 系）潜变量流 →
  Sparconv-VAE 解码 → Sparcubes 稀疏可变形 MC → 水密 1024³ 网格。
  这解释了它对外强调的"几何精度/可直接打印"。

### 4.4 可得性

- **代码不开放**：项目页原文 "Code may be released upon the approval of
  Math Magic"；GitHub `lizhihao6/Sparc3D` 只有 README/项目页；
  HF Space `ilcve21/Sparc3D` 的 `app.py` 实测**只是一个 iframe**，
  指向 `https://3dserver.hitem3d.ai/`（产品后端），**没有任何推理代码或权重**。
- `[无]` 未找到 Sparc3D 权重（HF 搜索无模型仓库）。
- 可借鉴的是**方法**（稀疏可变形 MC + 稀疏 VAE + TRELLIS flow 微调），
  不是代码。

---

## 5. Hi3DGen（开源，MIT）— 与 hi3d.ai 不同公司的可用近似

`[代码]` 本地仓库 + `Stable-X/trellis-normal-v0-1/pipeline.json` 实测：

- 表示/生成：**TRELLIS 架构**（sparse structure flow + SLAT flow +
  slat_decoder_mesh_swin8_B_64l8m256c），但两个 flow 都是
  **normal-conditioned** 变体（`ss_flow_normal_dit_L_16l8`、
  `slat_flow_normal_dit_L_64l8p2`）。
- 条件：输入图先经 **BiRefNet** 抠图 → **法线估计**
  （`Stable-X/stable-normal-v0-1` / `yoso-normal-v1-8-1` /
  `trellis-normal-v0-1`）→ 法线作为几何先验注入两阶段 flow。
- 采样（pipeline.json）：两阶段均 **25 步、CFG 5.0、cfg_interval
  [0.5,1.0]、rescale_t 3.0**；图像条件 **DINOv2 ViT-L/14-reg**。
- 权重体量：ss flow 1.12 GB + slat flow 1.20 GB + decoders 0.33 GB
  （fp16）+ DINOv2；运行要求 Python 3.10、torch 2.4 CUDA、
  `spconv-cu`、`xformers`（**无 MPS/CPU 路径**）。
- 机理含义：**"用法线把 2D 细节桥接到 3D"**——相比纯图像条件，法线图
  显式携带表面朝向与高频细节，几何保真度更高；这也是它和 TripoSG
  （SDF 隐式监督）的核心区别。

---

## 6. Meshy — 机理调研能到哪一步

`[无]` 公开论文 0、公开代码 0、相关专利 0（Google Patents assignee
`Meshy`/`Meshy LLC` 查询返回 0；`Meshy.ai` 只有营销/文档）。
`[厂]` 能确认的只有产品参数：
- 两阶段 **preview（几何）→ refine（贴图）**，与 Tripo/Hi3DGen 的
  "先形状后纹理"一致；
- `smart-topology`（T2/T2.5）：**指定面数直接生成 + 原生分离部件 +
  仅三角面**，说明它有一个产物级拓扑约束的生成模型（或强后处理），
  但架构未披露 `[推]`；
- `geometry_resolution: 2k/4k`（Ultra pass）：用体积分辨率作为质量档，
  暗示其生成/提取管线也是体素化路线 `[推]`；
- 8K 纹理、emission、remove_lighting：贴图阶段独立模型 `[厂]`。
**结论：Meshy 的机理不可复现，只能按产品行为（面数、部件、分辨率档）
归纳出"它至少具备哪些能力"，不能得到算法。**

---

## 7. 机理对照表

| | TripoSR | TripoSG | TripoSF | Hi3DGen | Sparc3D (Hi3D) | Meshy |
|---|---|---|---|---|---|---|
| 表示 | triplane NeRF | SDF 潜变量 | SparseFlex（稀疏等值面） | SLAT | Sparcubes（稀疏可变形 MC） | 未披露 |
| 生成器 | feedforward transformer | rectified-flow DiT（21 层/2048） | 仅 VAE 发布 | TRELLIS flow（normal 条件） | TRELLIS flow 微调 | 未披露 |
| 条件 | 图像 | 图像（DINOv2） | 点云+法线 | 图像+法线 | 图像 | 图像/文本/多视图 |
| 分辨率 | triplane 32² | 2048 tokens → 高分辨 | 256→**1024³** | SLAT 64ch | **1024³** | Ultra 2k/4k 档 |
| 推理配置 | 1 步 | 50 步 CFG 7 | VAE 前向 | 25 步 CFG 5 | 25 步 CFG 3.5 | 未披露 |
| 水密/可打印 | 否 | 需后处理 | **是（VAE）** | 否 | **是（论文卖点）** | 有打印线 |
| 代码/权重 | MIT 全开 | MIT 全开 | MIT（仅 VAE） | MIT 全开 | **gated** | 无 |
| 显存 | ~6GB | ≥8GB | ≥12GB | 未标注（CUDA） | 未标注（CUDA） | — |

---

## 8. 对 OpenFigura 的意义（机理层）

1. **我们的 pixal3d = TRELLIS.2 家族**，与 TripoSG/SF、Hi3DGen、Sparc3D
   同源（稀疏体素潜变量 + flow + 等值面）。这解释了我们的短板也指出了
   升级路径：
   - 想要**更锐利几何**：TripoSG（SDF-VAE + rectified flow，MIT，≥8GB）
     是直接可替换/可对照的后端；
   - 想要**水密/可打印**：TripoSF 的 SparseFlex VAE（MIT，≥12GB）可以
     当**后处理**——把任意网格重建成 1024³ 水密网格，正好补上
     `print-check` 之外的"可打印化"能力；
   - 想要**细节保真**：Hi3DGen 的 normal-bridging（MIT）是第三条路线，
     代价是法线证据链（输入法线图、归一化逆变换都要入账）。
2. **Sparc3D 说明"水密化"本身是关键竞争力**：<30s 的稀疏可变形 MC
   是产品级优势，但代码不可得。我们能走的合法近似是 TripoSF VAE
   （重建）或 FlexiCubes/开源 MC（几何工具），但**不获取、不使用**其未公开权重。
3. **Meshy 不可复现**：把它的 T2/T2.5 当作"对手能力边界"参考即可，
   不投入复刻；它的"原生部件"与我们的 PartCrafter 路线是同一目标。
4. **工程判据**：以上三条开源线全部要求 CUDA（spconv/xformers 或
   torch SDF 解码），与本仓库既有 MIA/UniMate 的"CUDA 机器"路线一致；
   接入前按 `docs/engineering/upstream-reuse.md` 记录来源、许可证
   （均 MIT）、权重哈希与推理日志，Mac 侧只登记为 unavailable。

### 建议的验证顺序（等拍板，不自动执行）

1. 在 CUDA 机器上跑 **TripoSF VAE**：拿我们现有 958k 三角的 scifi 资产，
   重建 1024³ 水密网格，记录显存/耗时/偏差（对 `print-check` 是真补强）。
2. 跑 **TripoSG** 对同一张 golden 输入出模型，与 pixal3d 的产出一并
   渲染对照（不评测画质优劣，只记录差异与耗时）。
3. **Hi3DGen** 作为第三条对照，重点记录法线图与输入归一化的可复算性。
4. Sparc3D 只做论文级跟踪（等代码释放），不排期。

---

## 9. 限制

1. 未运行任何模型；显存/速度均为 README/论文口径，不是本机实测。
2. Tripo 商业模型（P2.0/Nexus、v3.1）与 Meshy 的机理均为 `[推]` 或
   `[无]`；产品参数不等于训练方法。
3. `TripoSF` 只发布了 VAE，不代表 Tripo 产品的生成器就是它；
   "同源"是架构层面的合理推断。
4. 专利负向检索只覆盖 Google Patents 的 assignee 字段与有限关键词，
   不代表不存在未公开申请。
5. Sparc3D 的 "code may be released upon approval" 是项目页当前表述，
   后续可能变化；复用时以其官方发布为准。

---

## 10. 证据文件（`algorithms/`）

| 文件 | 内容 |
|---|---|
| `sparc3d-paper.html` / `sparc3d-paper.txt` | Sparc3D arXiv 全文（HTML + 纯文本，41k 字符） |
| `sparc3d-README.md` / `sparc3d-space.json` | 官方仓库 README、HF Space 元数据（app.py 只是 iframe） |
| `triposr-README.md` / `triposr-config.yaml` | TripoSR 说明与完整架构配置 |
| `triposg-README.md` / `triposg-model-index.json` / `triposg-transformer-config.json` / `triposg-vae-config.json` / `triposg-scheduler-config.json` / `triposg-inference.py` | TripoSG 管线、DiT/VAE 超参、推理默认值 |
| `triposf-README.md` / `triposf-1024.yaml` | TripoSF 说明与 SparseFlex VAE 配置 |
| `hi3dgen-trellis-normal-pipeline.json` | Hi3DGen 两阶段 flow 的采样配置与权重清单 |
| `meshy-patents.json` / `t23d-patents.json` | 专利负向检索结果（Meshy=0；Math Magic 仅 2D 特征映射） |
