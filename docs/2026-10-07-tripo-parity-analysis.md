# Tripo 对标与平替路径 — 2026-10-07

内部规划文档。调研时点 2026-10-07，结论只对 Tripo 官网/帮助中心/开发者文档
在此时点的公开表述负责。**厂商自述一律标 `[厂]`，独立第三方或实测标 `[验]`；
有冲突的数据直接写冲突，不取中间值。**

---

## 0. 一句话结论

**功能面上我们落后一大截，架构面上我们赢一局。** Tripo 是「模型 + 全流程工作台
+ 云 GPU + 计费」的完整产品，我们目前只有其中四个动词。
平替不是靠把功能列表补齐打勾，而是要选一组**他们结构上做不了的**场景做穿：
本机、离线、素材不外传、免费档也不丢 IP、每一步可复算。

需要说清楚的坏消息：**画质、速度、原生四边形拓扑、8K 贴图这四项，短期补不上**，
前两项是算力差距，后两项是训练差距。这不影响平替成立，但影响平替的适用范围。

---

## 1. Tripo 是什么（2026-10 时点）

**产品形态**：Tripo Studio（浏览器）+ Tripo API（开发者平台）+ 一堆引擎插件。

**模型线**：
- **P2.0**（2026-09-21 发布，接替 P1.0）— `[厂]` 自称业界首个原生生成四边形拓扑的
  3D 原生基础模型。**注意用词**：其首席科学家原文是 **quad-*dominant*（四边形为主）**，
  不是纯四边 [来源](https://3dprintingindustry.com/news/native-quad-meshes-arrive-in-ai-3d-generation-with-tripo-p2-0-255368/)。
  支持部件自动分离（身体/衣服/配饰，无技术细节公开）、面数预算
  （三角 ≤50,000 / 四边 ≤25,000）、一次出最多 4 个变体、区域重生成（Mesh Edit）、Smart UV。
  第三方报道明确标注这些主张**全部来自 Tripo 自述，未经独立验证**。
- **H3.1** — `[厂]` 高保真旗舰，最高 **200 万面**、最高 **8K 基础色贴图**
  （4K 法线 + ORM），面向英雄资产、特写、3D 打印。
- **P1.0 / Smart Mesh** — `[厂]` GDC 2026 发布，约 2 秒出结构化网格。
- **W1.0 / Project Eden** — 世界模型方向，早期研究。

**工作流模块**：AI 图像生成 → 模型生成 → 智能分割 → 重拓扑 → 贴图 → 绑骨动画
→ 导出/DCC 桥接。模块可自由组合。

**绑骨动画**（这部分我从开发者文档逐字核对过，可信度最高）：
- `POST /animations/rig-check` → `POST /animations/rig` → `POST /animations/retarget`
- 骨骼类型：`biped` / `quadruped` / `hexapod` / `octopod` / `avian` / `serpentine` / `aquatic`
- 骨骼命名：`tripo`（原生）或 `mixamo`（Mixamo 兼容）
- v1.0 模型 90+ 动画预设；v2.5 支持非人形
- 输出 GLB / FBX，输入上限 150MB
- 示例任务 `credits_consumed: 30.00`

**导出**：GLB/GLTF、FBX、OBJ、USD、USDZ、STL、3MF。
**插件**：Blender、Unity、Unreal、Godot、Maya、3ds Max、ZBrush、ComfyUI、Cocos。
**SDK**：官方 Python / JS SDK，另有官方 MCP server。

**计费**：网页端点数与 API 点数是**两套账**。
- 订阅（第三方口径混乱，仅作量级参考）：Free $0 / Pro ≈$20 / Max ≈$90 / Team ≈$55每座
- API 按量：1 credit = $0.01。图生3D 20–30 点，绑骨 25 点，重定向 10 点/条
- **免费档的商业条款是个大问题（⚠️ 未读到原文，见下）**：多个第三方来源一致
  引述用户协议 §5.2.1 —— 免费档下 Tripo（运营主体 Holymolly）保留用户输入与
  输出的使用/复制/修改/衍生/分发/转让/许可/变现权利，用户拿不到商用权；
  §5.2.2 才把权利给付费用户。

  > **可信度声明**：`tripo3d.ai` 域名对本机抓取返回 403，我**没有读到 §5.2.1 的
  > 原文**，该条来自第三方文章的一致引述（`[第三方]`）。正式对外引用前必须回
  > https://studio.tripo3d.com/terms.html 与 https://developers.tripo3d.com/zh/terms
  > 逐字核对。条款随时改，且有一个日本来源称免费档内容也**不被**用于训练，
  > 与「保留全部权利」的表述存在张力。
  >
  > 即便这条最终不成立，免费档**不可商用 + 输出强制公开**这两点已被多方印证，
  > 对独立开发者来说已经是足够的迁移理由。

---

## 2. 功能对比明细表

### 2.1 输入方式

| 能力 | Tripo | OpenFigura 现状 | 差距 | 补齐方式 |
|---|---|---|---|---|
| 单图生 3D | ✅ | ✅ `generate` + pixal3d 后端 | 无 | — |
| 文生 3D | ✅ | ❌ | 大 | TRELLIS.2 官方**也是单图**，无文本条件 → 需接别的后端，非配置问题 |
| 多视图输入 2–4 张 | ✅ | ❌ 且 `AGENTS.md` **明令禁止**喂多视图给单视图后端 | 大 | TRELLIS.2 官方不支持多视图（GitHub issue #10 确认），社区融合方案未验证 → 自研，成本高 |
| 草图/线稿输入 | ✅ | ⚠️ 取决于输入质量契约，`preflight` 会拦 | 中 | 扩 `input-quality.md` 的接受域，先做实验再改契约 |
| 输入质量门禁 | ❌ 无 | ✅ `preflight`（我们独有） | 我们领先 | — |

### 2.2 几何与网格

| 能力 | Tripo | OpenFigura 现状 | 差距 | 补齐方式 |
|---|---|---|---|---|
| **原生四边形拓扑** | ✅ P2.0 `[厂]` | ❌ 输出 ~10⁶ 面稠密三角网格 | **大（训练级）** | 短期不可补。折中：Quadriflow 重拓扑出四边化网格，但质量不等于原生四边 |
| 面数预算控制 | ✅ 三角 500–50k / 四边 500–25k | ❌ | 中 | Blender `decimate` + 目标面数参数，v0.2 `retopo` 动词 |
| Smart Lowpoly | ✅ | ❌ | 中 | 同上 |
| 区域重生成 Mesh Edit | ✅ | ❌ | **大** | 需要局部条件生成能力，现有后端没有 → 先不做 |
| 一次多候选（≤4 变体） | ✅ | ❌ 单次单结果 | 小 | 跑多次不同 seed 即可，本质是并发问题 |
| 部件自动分割 | ✅ | ❌ | 中 | 已 clone 未集成：PartCrafter、HoloPart（VAST 同团队，做部件级分解） |
| 生成耗时 | `[厂]` ~2 秒（P1.0 云端） | 实测 ~27 分钟（M5/16GB, `[验]`） | **结构性** | 不可补。云端 GPU 集群 vs 一台笔记本，认了 |
| 输出画质 | 商业调优，闭源 | 不作承诺；2026-10-07 八例复核判**不可用** | **大** | 诚实地说：这是我们最弱的一项 |

### 2.3 贴图与材质

| 能力 | Tripo | OpenFigura 现状 | 差距 | 补齐方式 |
|---|---|---|---|---|
| 自动 PBR（albedo/MR/normal） | ✅ | ✅ 由后端产出 | 无 | — |
| 8K 基础色贴图 | ✅ H3.1 / Max 档 | ❌ atlas 2048 | 中 | 升采样 + 重烘焙；先证明 4K 有意义再谈 8K |
| 贴图局部精修 | ✅ AI Texturing 可编辑 | ⚠️ `refine-texture`（image-to-3dlab ROI 投影，实测 8.54s） | 小 | 已有，继续做 ROI 门控 |
| Smart UV 一键展开 | ✅ | ❌ | 中 | Blender Smart UV Project 或 xatlas，成本低 |
| 抠图/背景处理 | ✅ | ✅ BiRefNet 自动抠图 | 无 | — |

### 2.4 绑定与动画 — **这是我们最大的空洞**

| 能力 | Tripo | OpenFigura 现状 | 差距 | 补齐方式 |
|---|---|---|---|---|
| 自动绑骨 | ✅ 单次前向 2–5 秒 `[验]` | ❌ | **大** | **UniRig**（MIT，SIGGRAPH 2025）——注意这是 **Tripo 自家 VAST 团队开源的** |
| 蒙皮权重 | ✅ | ❌ | **大** | UniRig 第二阶段；但官方仓库目前**只放出了骨骼预测**，权重模型标注 "coming soon" |
| 非人形绑定 | ✅ v2.5（四足/鸟/蛇/鱼/六足/八足） | ❌ | 大 | UniRig 支持多类生物 |
| 动画预设 | ✅ 90+ 条 | ❌ | 大 | 开源 mocap：LAFAN1 / CMU；或自己写 |
| 动画重定向 | ✅ `retarget` | ❌ | 大 | Blender 重定向 + 开源 mocap |
| Mixamo 兼容命名 | ✅ | ❌ | 小 | 命名映射表，成本低 |

> **UniRig 的硬约束**：需要 CUDA GPU >8GB 显存 `[验]`。本机 M5/16GB 是 Metal，
> **跑不起来**。这是 v0.2 绑骨路线的头号风险，必须在写代码前先解决
> （换 CUDA 机器 / 找 MPS 移植 / 退回 Rigify metarig 拟合）。

### 2.5 导出与集成

| 能力 | Tripo | OpenFigura 现状 | 差距 | 补齐方式 |
|---|---|---|---|---|
| 导出格式 | GLB/GLTF、FBX、OBJ、USD、USDZ、STL、3MF | 仅 GLB | 中 | Blender 本身全都能转 → `export --format` 透传即可，**低成本高收益** |
| 引擎插件 | Blender/Unity/Unreal/Godot/Maya/3ds Max/ZBrush/ComfyUI/Cocos | ❌ | 大 | **建议不补**：文件 + DCC 是更好的集成面 |
| Python / JS SDK | ✅ 官方 | ❌ | 小 | CLI 已有；薄封装即可 |
| MCP server | ✅ | ✅ `figura_*` | 我们更原生 | — |
| 本地 Web UI | ✅ Tripo Studio | ❌（v0.4 计划 localhost UI） | 中 | 按 ROADMAP v0.4 走 |

### 2.6 运行、成本与信任 — **我们赢的地方**

| 维度 | Tripo | OpenFigura |
|---|---|---|
| 生成在哪跑 | 他们的云 | **你的机器** |
| 参考图是否离开本机 | 上传 | **永远不** |
| 能不能离线 | 不能 | **能** |
| 价格 | Free / ~$20 / ~$90 / ~$55每座 | **免费（AGPL）+ 电费** |
| 免费档商业权利 | ❌ 不可商用 + 输出强制公开；是否保留 IP 待核（§5.2.1 `[第三方]`） | **✅ 生成物归你** |
| 并发 | 1 / 10 / 100 / 200（按档） | 单机串行（无上限但受硬件限） |
| 硬件门槛 | 无（有网就行） | Apple Silicon Metal 或 CUDA |
| 同 seed 可复现 | 服务端管线不透明 | **✅ 同输入 + 同 seed → 同 GLB** |
| 审计账本 | 只有平台历史 | **✅ `provenance.json`：命令/哈希/退出码/耗时** |
| 开源 | 闭源 | **✅ AGPL-3.0** |
| 遥测 | 有 | **无** |
| 自托管 | 不行 | **可以，AGPL 保证服务化也得开源** |
| 批量 / CI | API 计费 | **本地跑，零边际成本** |

---

## 3. 差距分级

**A 类 · 结构性差距，认了，不要假装能补**
1. 生成速度（云端 GPU 集群 vs 一台笔记本）
2. 输出画质（商业调优 + 大算力训练）
3. 原生四边形拓扑（P2.0 是训练出来的能力）

**B 类 · 性价比高，先补这些（低成本 / 高感知）**
4. 多格式导出（FBX/OBJ/STL/USD）—— Blender 已具备，纯透传
5. Smart UV 展开 —— Blender 一个 operator
6. 面数预算 / decimate —— `retopo` 动词的第一半
7. 部件分割 —— PartCrafter / HoloPart 已 clone

**C 类 · 贵但必须补，否则「平替」不成立**
8. **绑骨 + 蒙皮** —— 没这个，产出进不了引擎，前面全白做
9. 重拓扑 + 烘焙 —— 绑骨的前置条件

**D 类 · 建议明确不做**
10. 引擎插件矩阵（9 个 DCC 的维护成本 >> 收益）
11. 区域重生成 Mesh Edit（需要局部条件生成，与「后端可替换」架构冲突）
12. 世界模型
13. 云端服务与并发（ROADMAP 已列为 non-goal，且 AGPL 本身就是防线）

**E 类 · 可选，看用户要不要**
14. 文生 3D —— 开源侧没有现成的强文本条件后端
15. 多视图输入 —— TRELLIS.2 官方不支持，要自研融合

---

## 4. 平替路线图

原则：**先补「产出能不能进引擎」这一条链路**（C 类），因为它是平替成立的
最小充分条件；再补 B 类提升手感；A 类全程不碰。

### v0.2 — 让它能动（在现有 ROADMAP 上收敛）

顺序不能变，每步都要有真实渲染当证据：

1. **`retopo`** — Blender Quadriflow + 目标面数。**先做这个**，零新硬件依赖，
   且是后面所有步骤的前置。
2. **`bake`** — 高模→低模法线/贴图转移。Blender 已具备。
3. **`rig`** — **先解决 UniRig 的 CUDA 依赖问题再写代码。**
   三个备选：a) 找一台 CUDA 机器当 rig 后端；b) 验证 MPS 移植可行性；
   c) 退回 Blender Rigify metarig 拟合（质量降级但能跑）。
   *这一步是整个路线图里唯一有「可能做不成」风险的地方。*
4. **`skin-check`** — 权重可视化 + 固定姿势形变渲染 + 坏区自动报告。
   这条是我们相对 Tripo 的差异化能力：他们给你一个绑好的模型，
   我们给你**一份可核对的形变证据**。
5. **`animate`** — 导入 LAFAN1 / CMU mocap，Godot 真实帧验证。

### v0.3 — 补工作流闭环（B 类）

6. `export --format fbx,obj,stl,usd,usdz,3mf` — 透传 Blender 导出
7. `uv` — Smart UV / xatlas 展开
8. `segment` — PartCrafter / HoloPart 适配器（注意：PartCrafter 官方 runner 会在
   部件为空时塞一个退化网格，适配器**必须拒绝**而不是记成有效结果）
9. 面数预算参数贯通 `generate` → `retopo` → `export`

### v0.4 — 界面与分发

10. localhost 只读 Web UI（任务浏览 / 渲染画廊 / 账本查看 / 一键重跑）

### 不排期

多视图输入、文生 3D、区域重生成、引擎插件、8K 贴图。

---

## 5. 平替什么时候算成功（可证伪）

不写「画质追平」，写能验的：

1. **同一张角色参考图**，从 `preflight` 到「在 Godot 里放着 idle/walk 动画跑起来的
   带骨骼资产」，**全链路一本 provenance 账**，可重跑。
2. 这条链路里**没有任何一步需要联网**，参考图 SHA-256 在账本首行，全程没出过本机。
3. 对照成本：Tripo 侧完成同样链路要付 生成 + 分割 + 重拓扑 + 贴图 + 绑骨 的点数
   （按公开 API 价目，粗算 100+ 点），我们侧成本为 0，代价是时间与画质。
4. **做不到就直说**：如果第 1 条在 v0.2 结束时仍跑不通，那「平替」这个词
   在公开表述里就必须收回，只说「本地生成工具」。

---

## 6. 给对外表述的三条硬规矩

延续 `AGENTS.md` 的「Evidence or it didn't happen」：

1. **不说画质**。没有同输入对照实验，就不出现「媲美/接近/不输」这类词。
2. **说平替时限定范围**：平替的是「上传素材换模型」这个**工作流与信任结构**，
   不是模型质量。这是 README 里已经写死的口径，对外沿用。
3. **A 类差距主动写出来**。速度、画质、原生四边拓扑，写在显眼位置比被用户发现好。

---

## 7. 来源

**Tripo 官方**
- 功能总览 https://www.tripo3d.ai/help/getting-started/what-features-does-tripo-have
- P2.0 发布 https://www.tripo3d.ai/blog/tripo-p2-0-preview ｜ https://www.tmcnet.com/usubmit/2026/09/21/10449134.htm
- P1.0 / GDC 2026 https://www.tmcnet.com/usubmit/2026/03/09/10344476.htm
- 原生四边拓扑报道 https://3dprintingindustry.com/news/native-quad-meshes-arrive-in-ai-3d-generation-with-tripo-p2-0-255368/
- **绑骨 API 文档（本文件核对最细的一份）** https://developers.tripo3d.ai/en/docs/animations-rig
- 点数机制 https://www.tripo3d.ai/help/credit/how-do-credits-work
- 套餐 https://www.tripo3d.ai/help/billing/which-tripo-ai-plan-is-right-for-me ｜ https://developers.tripo3d.com/zh/pricing
- 商用条款（免费档保留 IP） https://www.tripo3d.ai/ko/help/privacy-policy/how-to-use-tripo-models-commercially
- 阿里云百炼托管版 https://help.aliyun.com/zh/model-studio/tripo-h3-1
- 第三方实测（免费档 200 点实际只够 ~3 个成品资产） https://dev.to/titusbrett/tripo-ai-review-i-ran-the-free-tier-through-a-unity-asset-pipeline-and-heres-what-survived-5fan

**开源侧可补件**
- UniRig（MIT，VAST/Tripo 同团队，SIGGRAPH 2025） https://github.com/VAST-AI-Research/UniRig ｜ https://ar5iv.labs.arxiv.org/html/2504.12451
- MeshAnything（ICLR 2025，三角网格，非四边） https://github.com/buaacyw/MeshAnything
- TRELLIS.2（MIT，官方**仅单图**，无多视图/无绑骨） https://github.com/microsoft/TRELLIS.2/issues/10 ｜ https://huggingface.co/microsoft/TRELLIS.2-4B
- 仓库内已有调研：`docs/2026-10-07-upstream-integration-rigging.md`（UniRig / Rigify / PartCrafter / Hi3DGen / DetailGen3D / Hunyuan3D-2.1 的边界）

**条款原文（本机 403，未读到，需人工核对）**
- 用户协议 https://studio.tripo3d.com/terms.html
- 开发者条款 https://developers.tripo3d.com/zh/terms ｜ https://developers.tripo3d.ai/ko/terms

**数据冲突声明**：订阅价格第三方口径互相矛盾（Team 档有 $55 / $109.90 / $329.70每座三种说法），
免费档点数有 200 / 300 两种说法。本文件不取平均，只标量级；定价决策前须回官网复核。

**本文件的证据强度**：唯一被我**逐字读到原文**的是绑骨 API 文档
（`developers.tripo3d.ai`）。其余来自搜索引擎对 Tripo 页面的摘要 + 第三方报道，
标 `[厂]` 的是厂商自述、`[第三方]` 是转述。**用于对外材料前，逐条回原文核对。**

---

## 8. 待办（需要人类拍板）

- [ ] UniRig 的 CUDA 依赖怎么解？这决定 v0.2 绑骨能不能做，**建议优先处理**
- [ ] 要不要把「多格式导出」提前到 v0.2？成本极低（透传），但对外感知强
- [ ] 本文件是否需要英文版并入公开仓库（目前是中文内部文档）

---

## 9. 补记 · 2026-10-08 当晚实测（追加，不改上文）

- **B 类第 5/6/7 项已真实落地**（`codex/3d-loop`，执行器阶段记录）：
  `optimize` ratio=0.1 在 958,816 三角形真实网格上 6.75 s → 95,881；
  `uv`（smart project）1.12 s；`retopo` 管线为 weld→体素水密→QuadriFlow，
  QuadriFlow 对生成网格如实 CANCELLED 后**保留水密三角结果**（240,052 面，
  单向偏差 max 0.0059），报告写明需重烘焙。结论不变：后处理重拓扑可用，
  但"可动画级四边布线"仍未达标——这条差距是真实的，不是营销。
- **语义部件分割缺失被实测确认**：`segment` 按连通分量给出 8,090 个噪声块，
  护栏正确拒收。部件自动分离（P2.0 卖点之一）必须走 PartCrafter/HoloPart
  这类学习式后端，拓扑算法平替不了它。
- **C 类第 8 项风险比本文预估更大**：scifi 网格 retarget 到 Mixamo 行走
  每帧出现 1,000–1,533 个手部三角形深穿插，三代局部 IK 修正均不收敛
  （数据存 scifi-motion 阶段账本）。即"绑好≠能动"，重定向路线对生成网格
  近乎失效——这使 UniMate（无重定向直接生成）和部件级方案优先级上调，
  调研见 docs/2026-10-08-unimate-review.md。
- **速度口径（2026-10-08 用户拍板）**：不与 Tripo 拼云端秒出。27 分钟是硬件
  下限非上限；定位改为「deliberately not cloud-fast：速度归用户的硬件，浪费
  归零，每个数字都带账本」。任何对外速度数字须先由 CUDA 基准矩阵实测（loop L14）。
  正式口径见 `docs/product.md`「Speed stance」。
- **对 P2.0 宣传本身**：其首席科学家原文为 quad-*dominant*（§1 已录），
  至今无独立第三方验证发布。对外口径继续沿用 §6 三条硬规矩。

---

## 10. 补记 · 2026-10-16 公开资料核对（追加，不改上文）

对 `studio.tripo3d.ai/zh` 的公开页面与公开静态资源做只读观察后，本文多处"公开报道"
升级为实测：`docs/2026-10-16-tripo-studio-feature-review.md`（证据在
`.local/runs/2026-10-16-tripo-studio-review/`）。

- **P2.0 落地形态确认**：studio 内即 **Smart Mesh**（`tab=smart_mesh`，
  banner campaign `smart_mesh_p2_preview`），模型 id `Nexus-v2.0-20260801`，
  100 点/次；四边重拓扑另有服务侧三分法（三角 5 / 四边 10 / SmartPoly 30）。
  §0「原生四边形拓扑短期补不上」判断不变；新增对外说法：四边在他们那里
  也是**模型级付费能力**，不是免费算法。
- **计费修正**：studio 侧 rigging=20（API 侧 25，两套账确认）；完整 43 项
  Credits 价目表已提取，Full chain ≈105 点，§5 第 3 条"粗算 100+"成立。
  **Segmentation=40 是全表最贵常规操作**，与 §9 补记"语义分割缺失被实测
  确认"互相印证。
- **新增功能面**（bundle 实证，本文未录）：对称检查 API、导出 DCC 预设
  （9 个 DCC、端口 60600–60690）、使用场景预设（10 类 use_case）、
  uv 编辑、8K 纹理常量、**Agentic Canvas（forge3d，allowlist 灰度）**。
- **隐私对照**：首页即加载 PostHog（会话回放钩子常量在 bundle 内）+ 自研
  事件管线 + 11 个营销像素。「素材不出本机」叙事之外，**行为数据也不外流**
  这点现在是实测差距，可用于对比材料。
- **借鉴清单**见新手册 §8：立刻可做（导出预设 / use_case / 对称检查入
  preflight / 面数预算默认值）、观望（Smart Mesh 进化、Agentic Canvas）、
  明确不学（计费、遥测、DCC 插件矩阵）三类。
