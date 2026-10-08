# UniMate 深度调研（2026-10-08）

Repo：`~/Desktop/Local/Opensource/UniMate` @ `b78c780`（2026-10-08 当日有推送）。
论文：arXiv 2609.05415，SIGGRAPH Asia 2026（Princeton/Berkeley/MIT/NTU）。
**许可证：代码 MIT；发布权重 CC BY-NC 4.0**（README.md:337）——非商业权重
与 OpenFigura 的 AGPL + 商用自由产物立场冲突，接入时必须作为独立许可的
可选后端记录，产物商用前需取得授权或自训权重。

## 它是什么
给定**已绑定骨架**的资产 + 文本提示，直接在该骨架自身的规范坐标系里生成
动作（flow matching，60 帧 @30fps，实测单步 50 次 ODE），
**没有重定向这一步**（data_process/rig_preprocess/README.md:48）。
附带三种替换式采样：关键帧补间、指定关节保留的动作编辑、多段提示串联。
驱动网格复用资产自身的蒙皮权重，经 `blender -b` CLI 出 GLB+FBX
（data_process/mesh_animation/animate_motion.py:376-380,
blender_rig.py:707-843），joint 顺序有 cond/GLB 双重校验（sample_manifest.py:109-181）。

## 对我们痛点的判断
1. **结构性绕开 scifi 困境**。今晚 L07 失败的本质：Mixamo 行走剪辑重定向到
   MIA 骨架后，双手每帧 1000+ 三角形埋进大腿（v5 报告 `before_correction`），
   两骨 IK 局部推挤已被证明修不动。UniMate 从不把外部剪辑搬进目标骨架，
   动作生成本来就在"这个骨架自己的空间"里。
2. **但它不管碰撞**。全库扫描 `collision|penetrat|intersection|skate|contact`
   无任何接触检测/修复/惩罚项——损失只有 masked-L2 + 旋转测地 + 速度平滑
   （models/flow/transport.py:127-161）。它的论文立场也未承诺无穿插。
   **OpenFigura 的区域接触闸仍然是不可替代的验收器**：生成 N 份样本
   （--num_repetitions）→ 全部过我们的 62 行×31 帧检查 → 只交付干净样本。
   "模型不保证、工具层保证"——这正好是 OpenFigura 的存在理由。
3. **接入门槛要如实记录**：
   - 推理需要 CUDA（device 默认 cuda，sample.py:1296；改 config 可 CPU 但慢）：
     torch 2.5.1+cu124、Python 3.10、torch_geometric、`Motion` git 库为硬依赖；
     采样本身不需要 bpy（bpy==4.0 是 cp310 数据管线/渲染用）——隔离 conda
     环境 + 用我们自己的 Blender 5.2 CLI 驱动网格是可行组合。
   - 权重下载：`hf download Linzhan/UniMate`（150k step 检查点，
     num_layers=10/latent 512，参数量未公布）。VRAM 需求文档未给出，未验证。
   - rig_preprocess 是 CPU 流程（秒到一分钟/资产），但关节标注默认调
     DeepSeek/OpenAI API（joint_annotation/llm.py:33-37）；有离线 `rule`
     回退与 `--backend local`，且默认停在人工审查步——符合我们的
     输入质量门哲学。
   - 关节预算 ≤71（pipeline.py:109），MIA 52 关节可进；但 mixamorig 全量
     ~65 骨在"未见骨架"警告区（README.md:279）；**重复骨名会坍缩成占位标签
     并消耗预算**（review.py:219-220, motion_features.py:174-179），入库前
     要做唯一性检查。facing pair 需水平可分（annotate.py:159-167）。
   - ComfyUI 封装已存在：`jethac/ComfyUI-UniMate`（MIT，文本→动作→动画
     GLB），对我们的 ComfyUI 工作流复现有参考价值（未调研）。

## 结论与计划
- 列为 **motion 生成后端候选 `unimate`**（capabilities 如实报：需 CUDA +
  NC 权重许可确认），接入口径：`rig_preprocess` 产 cond → `inference.sample`
  → Blender 驱动 → **现有 retarget 接触闸同款 evaluate 作为验收器**。
- 前置实验（有 Windows GPU 后）：拿 scifi 的 `model-autorig.glb`（先查重复
  骨名）跑 "An object walks forward." ×3 reps × 我们的检查，对照今晚
  retarget 的 1287 穿插——用同一把尺子比较两条路线。
- 与 SkinTokens 同属"外部神经骨架/动作"家族：调度、许可、下载归 L05。
- 今日 retarget 修正的负结果（候选探测 IK 推挤救不回深穿插）保留在
  mesh-chain/scifi-motion 阶段记录中，不覆盖。
