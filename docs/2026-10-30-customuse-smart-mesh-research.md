# Customuse Smart Mesh AI 调研

日期：2026-10-30。截图中的产品对应 Customuse 的 Smart Mesh AI / Adaptive
Character Clothing Tool 方向。

## 它实际解决什么

Customuse 官网把自己定位成一个托管式 3D 创作工作台，整合 Meshy、Hunyuan 3D
等模型，并提供生成、纹理、编辑、动画和导出流程。近期公开信息显示，Smart Mesh
AI 的首个工具是 Adaptive Character Clothing：输入人体角色和衣服网格，自动把
衣服适配到不同体型，并带几何感知和布料模拟控制。它是 mesh processing / garment
fitting，不是新的图生 3D 基础模型。[Customuse 官网](https://customuse.com/)

官方没有公开 Smart Mesh AI 的源码、权重或本地安装包。它是托管式 beta 服务，
所以截图里的“衣服自动适配”不能直接迁入 OpenFigura，也没有开源许可证可以让我们
复制实现。第三方报道也将其描述为 paid hosted beta，具体价格和 MCP 发布时间
属于二手信息，不能当作接口已经可用。[报道](https://artrealmai.com/article/customuse-smart-mesh-ai-adaptive-character-clothing-tool)

## 对 OpenFigura 最有价值的部分

这条路线正好对应我们当前的裤面撕裂问题，但要拆成可审计的几个阶段：

1. **Garment intake**：识别衣服网格、人体网格、衣服边界、厚度、开口和碰撞层。
2. **Body-conditioned fitting**：沿人体表面或骨骼姿态适配衣服，保留衣服原始
   UV/材质，并记录是否发生重叠或穿透。
3. **Sewing / contact constraints**：衣服内部不能穿进人体，袖口、裤腰、领口
   等开口需要独立约束，不能只靠整体 shrinkwrap。
4. **Rest-pose skin transfer**：衣服继承身体骨架时，衣服权重不能把手指影响传播
   到裤腿；应使用区域锁定和固定姿态探针。
5. **QA gate**：静态贴合、多个动作帧、三角拉伸、碰撞和近景渲染都通过后，才允许
   进入 export。失败候选隔离，原衣服和人体不覆盖。

这意味着 OpenFigura 需要一个独立的 `garment-fit` / `cloth-adapt` 方向，不能把
它塞进 `mesh optimize` 或 `motion gate`。现有 skin-check、skin-probe、motion-gate
可以作为下游验证器，但当前尚未实现自动服装适配。

## 可复用的开源替代和邻近技术

- Blender 原生 cloth simulation、shrinkwrap、surface deform、mesh transfer：
  可作为确定性基础，但需要 OpenFigura 自己包装输入快照、参数和验证报告。
- Rigger：已有权重锁定、区域蒙皮、修正权重和重定向经验，适合补服装绑定后的
  质量检查，不是 Customuse 的自动服装拟合替代。
- Blender Skills 的 `cloth-sim`、`collision-proxy`、`asset-optimization`：
  可借鉴工作流和 QA 清单；它们是 MIT Skill 文档，不提供服装拟合模型。
- TailorNet、Garment4D、SIZER、CLO/Marvelous 相关研究：可调研算法，但模型、
  数据集、人体/服装许可要逐项核查，不能因为论文开源就直接用于 OpenFigura 的
  商业默认后端。

## 当前判断

Customuse 的关键差异不是“又一个更强的生成模型”，而是把生成后的脏网格继续
做成可穿戴、可换装、可导出的资产。OpenFigura 应该吸收这个产品层思想，形成：

`body + garment + rest rig → garment fit → skin/contact probe → motion gate → export`

优先在现有小满模型上做一个简单裤装或袖子基准，先证明静态贴合和两三个固定动作
帧，再扩展到全身衣服。不能把 Customuse 的宣传视频当成我们已实现的质量证据。

本轮未登录 Customuse、未上传用户资产、未安装未知插件，也未复制任何闭源代码。
