# RuiC-PoseAtlas 对 OpenFigura 的参考库价值

上游：[HRuiCcc/RuiC-PoseAtlas](https://github.com/HRuiCcc/RuiC-PoseAtlas)，
固定提交 `cc1f0b72575a88272f31ac75edf49fbc94902dc9`。

## 它是什么

RuiC-PoseAtlas 是一个纯静态、零运行时依赖的三语参考站，不是 3D 生成器、
动作模型或 Blender 插件。当前仓库 README 记录三套内容：

- 288 组人体姿态、1,439 张人台线稿，每组最多正面、斜侧、侧面、俯视、仰视五个视角。
- 1,407 套无人衣装，带季节、品类、颜色、材质、版型和配饰标签。
- 1,499 张 AI 虚构人像，分脸部与造型、发型等筛选。

它的核心价值是把“姿态、衣装、脸”分开检索，再组合成一组稳定的角色参考，
这正好对应 OpenFigura 目前输入质量和脸部一致性不足的问题。

## 对 OpenFigura 的可用部分

1. **输入参考选择器**：在 `preflight` 前增加可选的 reference catalog，保存
   pose/costume/face 的来源、语言标签、视角和 hash；生成任务只接收用户明确
   选中的图片，不让 Agent 随机拼多视图。
2. **角色 brief**：把姿态、脸和衣装分别列为输入槽位，生成后在 ledger 中记录
   `pose_reference`、`face_reference`、`costume_reference` 三个来源，便于复现和
   前后候选比较。
3. **脸部近景工作流**：人像图鉴可作为脸部 ROI 的参考集合；实际建模仍需要
   landmark/visibility/UV 约束，不能把人像图直接当成纹理或几何真值。
4. **五视角检查**：它的同姿态多角度组织方式可用于 OpenFigura 的 candidate
   compare 和 Blender QA 视图，但不能替代实际生成模型的多视角一致性。

## 许可证和风险

仓库 `LICENSE` 的 MIT 范围只覆盖作者编写的代码、样式、脚本和文档；README
明确排除 `img/`、`thumbs/`、原始记录、名称和元数据。图片仅允许作为参考和
创作参考，禁止重新分发、转载或转售图片数据。因此：

- 只保留源码仓库在 `~/Desktop/Local/Opensource/RuiC-PoseAtlas` 做研究。
- 不把其图片、脸库、衣装库或原始 JSON 复制进 OpenFigura Git。
- 如果未来做 `reference_catalog`，只存用户本地路径、来源 URL、hash、许可
  状态和用户选择，不复制受限图片。

## 与现有 OpenFigura 的边界

它不能解决脸部五官几何、蒙皮串权重、碰撞穿插、UV 烘焙或动画生成。它能补的是
输入端和审查端：让 Agent 先选定“哪张脸、哪套衣装、哪组姿态”，再进入现有
`preflight → generate → inspect → render → skin-probe/motion-gate → export`。
这比把图库图片直接喂给生成器更可靠，也不改变 OpenFigura 的本地、可审计架构。

## 本轮本地状态

已稀疏克隆到 `~/Desktop/Local/Opensource/RuiC-PoseAtlas`，只取 README、LICENSE、
HTML、data、assets 和 scripts 做结构研究，未下载完整图像资产。没有修改
OpenFigura 源代码、golden 或用户候选。本轮结论是参考库接入设计候选，不是
模型质量验证。
