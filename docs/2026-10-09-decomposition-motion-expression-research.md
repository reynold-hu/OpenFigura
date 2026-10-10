# 第二步：拆解、动作、表情控制 — 开源格局调研

日期：2026-10-09 深夜。核实等级标注：`[核]`=今日本地/官方源直接核对；
`[知]`=既有知识，本机今晚访问 GitHub 受限（API 限流+页面网关异常），
**接入前必须回原文复核**；`[验]`=已在 OpenFigura 真实跑过。

## 0. 先修正一步理解

"第二步=抓骨架+动作执行"大体对，但骨架不是从零：MIA 自动骨架已有两个
通过案例（bunny、scifi 低模）`[验]`，小满失败挂账。第二步实际是三件事：
**部件拆解**（没有）、**骨架/蒙皮**（半有）、**动作执行**（人形剪辑链可用，
生成式动作等 GPU）。表情控制是第三件事，与拆解正交。

## 1. 部件拆解（语义级，不是连通分量）

| 方案 | 做什么 | 许可/硬件 | 状态 |
|---|---|---|---|
| PartCrafter (NeurIPS 2025) | 结构化部件生成/分解，兼容 TripoSG/Hunyuan3D-2.1 向量集 | **MIT** `[核]`；推理 CUDA ≥8GB，训练 8×H20（与我们无关） | 已克隆 `Local/Opensource/PartCrafter`，未接入；GPU 闸 |
| HoloPart (VAST) | 部件级分解，SkinTokens 同团队 | 待核 `[知]` | **未克隆**——今晚网络不通，待复核 |
| SAM 3.1 分割工作流 | 图→部件 mask→逐件 3D | Studio setup 目录里有现成 ComfyUI 工作流（Parts/Part+Flux 变体）`[核]` | 我们的 ComfyUI 执行器缺位（L10），排后 |
| 我们的 `mesh segment` | 仅连通分量 | 已实现 | 对生成网格无效（8,090 噪声块 `[验]`），保留作诊断工具 |

结论：拆解首选 PartCrafter（MIT 干净、克隆在手），等 GPU 节点。
CPU 侧现在能做的只有几何诊断类（boundary/组件统计，已有）。

## 2. 动作执行全景

- **已有可用**：Godot 同名重定向 + Blender IK + 接触闸 `[验]`（bunny 全过；
  scifi 深穿插负结果 `[验]`）。适用边界已量化：贴合人形+手臂摆动小的剪辑。
- **UniMate** `[核]`（前晚深调）：文本→任意骨架，无重定向步骤，绕开深穿插
  类问题；NC 权重 + CUDA，双闸未解。
- **SkinTokens/TokenRig** `[核]`（克隆在手）：骨架+蒙皮生成（不是动作），
  14GB NVIDIA；对应我们的 autorig 升级线。
- `[知]` 待复核的其余候选：MDM/T2M-GPT/MLD 系（SMPL-X 条件，**SMPL-X 模型
  许可研究向**，不作默认后端）；Trumans/Apose（视频驱动人体姿态入场景，
  方向不同）。结论：不追新，GPU 到位后先跑 UniMate 对照，失败再评估。

## 3. 五官表情控制（本次新调研）

### 3a. CPU 薄切片（本机今天就能起步的路线）
**MediaPipe 52 个 ARKit blendshape 分数**已经在我们的 `face_landmarks`
输出里 `[验]`（head-sculpt 实测带出 blendshapes）。缺的下游：
1. blendshape 分数 → Blender **shape keys 驱动表**（52 键命名对齐 ARKit 规范）；
2. 前提：网格要有 morph targets。生成网格没有 → 两条供路：
   - **FLAME 2023 Open**（CC-BY-4.0 可商用 `[核]`，前晚文档已定调）：
     拟合形状+表情参数 → 把 FLAME 表情基**迁移**为角色 mesh 的 shape keys
     （对应关系=拟合时的顶点配准）；
   - **FaceVerse V4**（代码已 vendored `[核]`，含眼球/嘴/表情参数；
     **权重授权仍未核完** `[待]`）。
3. 风格化角色（Q 版小满）MediaPipe 检不出脸 `[验]` → blendshape 路线对它
   无效；Q 版表情走"几何带 + 手工/程序 shape keys"或等真人向参考。

### 3b. GPU 升级候选（全部 `[知]`，接入前必须复核许可与硬件）
- **LAM**（TencentARC）：单图→3DGS 头部化身 + LAM_Audio2Expression
  （音频→表情参数）。若 MIT 属实则是最完整开源讲话头方案。
- **ViTO**：音频→FLAME 表情系数，接 3a 的参数空间即插即用。
- **GaussianAvatars**（TUM）：多视角视频→FLAME 拟合，适合"给小满录表情库"。
- 2D 系（SadTalker/LivePortrait/AniPortrait）：产出是视频不是网格资产，
  **明确不进主线**，只作参考素材。

### 3c. 诚实边界
- 单张照片不能恢复看不见的几何（鼻翼侧面、耳后）——表情≠换脸，
  表情参数只驱动**已拟合身份**的可动部分。
- 任何"表情可用"声明必须过我们自己的闸：blendshape 幅度扫描 → 逐帧
  渲染 → 接触/穿插检查（复用 motion-gate 的 evaluate）→ 人工 visual_approval。

## 4. 建议执行顺序

1. **现在（CPU）**：`face_landmarks` 已带 52 blendshapes → 先做
   「blendshape 分数可视化报告」小工具（零新依赖，纯账本），把数据价值坐实。
2. **现在（CPU）**：FLAME 2023 Open 下载+许可落档（模型本体是用户获取），
   实现形状拟合的最小验证（head-sculpt 是真人向，正合适）。
3. **GPU 到位**：PartCrafter 拆小满 → 逐件 MIA/SkinTokens → UniMate 动作
   → 全链过闸；LAM/ViTO 先复核许可再排队。
4. **不做**：2D talking head 主线化、SMPL-X 默认后端、追新论文模型。

## 5. 今晚未核事项（网络受限）
- HoloPart、LAM、ViTO、GaussianAvatars、HumanRig 的许可证与硬件要求
  全部为 `[知]` 级，明日复核后才能进对账矩阵。
- GitHub API 限流 + raw/页面网关异常，非仓库不存在（TencentARC/LAM 的
  404 与已知事实矛盾，判定为通道问题）。

## 6. 执行结果（同夜追加，全部真实）

- **表情报告工具已落地**：`face_expression_report` 动词 + 执行器步骤 + CLI
  `face-expression-report` + MCP `figura_face_expression_report`；纯账本，
  不做新推理。真实运行 head-sculpt：@0.1 阈值 10 通道激活，
  top5 = mouthPucker 0.73 / eyeSquintLeft 0.66 / eyeSquintRight 0.34 /
  eyeLookUp L 0.31 / R 0.30——与雕塑表情吻合（撅嘴、眯眼、上视）。
  证据 `.local/runs/2026-10-09-expression/`。594 测试通过。
- **FLAME 2023 Open 获取路径实测**：`download_model.php?model=flame2023_open`
  返回 404（下载需 MPI 站点注册，属预期门控）；许可页确认 CC 条款与商用
  表述存在。**用户行动项**：注册 flame.is.tue.mpg.de 下载后由我们校验哈希
  并入 manifest。
- **无门控替代发现**：MPFB2（MakeHuman 系）本地评审记录确认
  **代码 GPLv3 / 资产 CC0**（`mpfb-review-2026-10-04/LICENSE.*`），且与
  FLAME 兼容；本地 mpfb-assets 子集含 skins/clothes/proxymeshes 但
  **不含表情目标文件**——expression targets 需从 MakeHuman 社区资产站
  无门槛下载。blendshape→shape keys 桥接（MediaPipe 52 分数 ×
  CC0 表情基）是下一个 CPU 工作日的主任务。

## 7. 表情位移场实测：CC0 资产可用，配准是拦路虎（2026-10-10）

- hm08 基网格（`makehuman/data/3dobjs/base.obj`，19158 顶点，CC0 仓库声明）
  上 targets 解剖分层正确：eyeBlink y=7.3 > mouthSmile 6.9 > jawOpen 6.8；
  jawOpen 平均位移 0.84cm、最大 3.87cm（分米制换算后合理）。
- **但轴向包围盒配准实测失败**：银巾角色（721,075 顶点）上 jawOpen 只带动
  250 个顶点且落在身高 71%（胸颈），eyeBlinkLeft 带动 0 个。风格化大头
  比例与写实 hm08 无法靠 bbox 对齐——位移场会在错误位置生效。
- 半成品 worker 已删除，不发布已知错位的管线。纯函数场模块
  （expression_field：OBJ 解析/稠密化/KD 最近点/衰减/合成）保留，603 测试。
- **配准的正解路径**（下次实施）：渲染角色正脸 → MediaPipe 2D 关键点 →
  结合渲染深度反投影 3D 头部锚点（眼/鼻/颌）→ 用锚点对 hm08 头部子集做
  相似变换配准 → 再进位移场。素材全在手上，工作量约一天；验收=配准后
  jawOpen 顶点必须落在角色下颌带（height-frac >0.85 且空间聚集）。
