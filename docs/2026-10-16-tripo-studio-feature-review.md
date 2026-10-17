> **定位**：OpenFigura 是独立开源项目（AGPL-3.0），目标与本文提到的商业
> 产品不同——本地运行、素材不出机器、每一步可复算。本文只做**公开资料下的
> 功能与架构调研**，用于决定我们自己要做什么；不复制、不复刻第三方产品，
> 也不使用其未公开的实现或权重。

# Tripo Studio 公开功能调研 —— 实测记录版 — 2026-10-16

对 `https://studio.tripo3d.ai/zh` 的**公开页面与公开静态资源**做了只读观察。
**本文只记录核对到的东西**：每一条都给出证据文件名（在
`.local/runs/2026-10-16-tripo-studio-review/`，gitignored）或公开 bundle 内的
提取位置。厂商自述、推断、未知分开标记：

- `[验]` — 本次在本机实测/静态提取到的事实（有证据文件）。
- `[推]` — 从代码结构做的有限推断，注明依据。
- `[厂]` — 来自 Tripo 官方公开材料（未在本机验证）。
- `[未知]` — 登录墙后或未抓取，明确写未知，不含糊。

本文不是对 2026-10-07 `docs/2026-10-07-tripo-parity-analysis.md` 的替代，
而是给它补上**第一份来自产品本身的证据面**：那篇几乎全部依赖公开文档和
第三方转述，这篇是从 studio 自己的 JS bundle、网络流量和 DOM 里挖出来的。

---

## 0. 一句话结论

Tripo Studio 是一个 **Nuxt 3 SPA（Cloudflare 前置）+ 自研微服务网关 +
Credits 计费** 的一体化 3D 工作台，功能面从生成一路铺到导出、DCC 桥、社区画廊。
本次在**未登录状态**记录了它前端公开 bundle 的构成（112 个 chunk，2.8 MB）和
51 个 `/v2/studio/*` 接口路径、43 项 Credits 价目表、8 个模型版本号、
7 类骨架、9 个 DCC 桥端口。**登录墙后的运行时行为未验证**，但静态面足够修正
上一篇 parity 文档里的多处不确定性（见 §7）。

对 OpenFigura 的直接价值：**三件事立刻可借鉴**（导出预设、使用场景预设、
对称检查），**三件事值得盯着**（Smart Mesh/quad 的落地形态、Agentic Canvas、
分割的 40 点数定价所印证的"语义分割是硬骨头"），**一批东西明确不学**
（计费、遥测基建、DCC 插件矩阵）。

---

## 1. 方法与证据链（可复跑）

工具：本地浏览器只读观察（本机构建 HEAD `180ba03bf`；旧版本 6.5.0
缺少采集预算参数，其余步骤可用旧版）。浏览器：Chrome 155，独立 profile
`/tmp/public-page-observation-profile`，CDP `127.0.0.1:9222`。

| 步骤 | 做法 | 产物（相对证据目录） |
|---|---|---|
| 1. 公开页面只读检查 | 读取 DOM/无障碍树、已加载脚本清单、观察窗口内的网络与存储键 | `01-inspect-page.json`（SHA-256 `6e9a7f53…`） |
| 2. 新会话启动被挡 | 干净的临时浏览器会话触发 Cloudflare 校验 | `04-scenario-capture.json`（`403` + Turnstile，见 §8） |
| 3. 公开网络端点梳理 | 只读 CDP 记录页面请求的域名与脚本地址 | `cdp-recon.txt`（23 个源、119 个 module 脚本） |
| 4. 已加载资源与响应记录 | 在现有会话中记录页面自身的请求与公开响应体 | `07-scenario-connect-capture.json`（19 MB；295 次请求，SHA-256 `79c57ed9…`） |
| 5. 公开脚本整理 | 把记录到的脚本字节按 URL 归位并核对摘要 | `08-exported-scripts/`（142 个源文件、7.6 MB、`manifest.json` SHA-256 `ec5370f6…`） |
| 6. 静态代码结构分析 | 对整理后的公开脚本做离线语法树分析（不执行页面代码） | `09-js-app-analysis.json`（240 MB；140 文件、228 模块、548 节点；SHA-256 `a571cc23…`） |
| 7. 截图 | 页面可见视口记录 | `10-studio-home.png`（`9e837a50…`，即本文件首页截图） |

**证据等级**：步骤 4/5/6 是主证据——脚本字节来自页面自身加载的公开资源，
逐文件 SHA-256 校验落盘（`manifest.json` 内含 142 条摘要）；bundle 提取均
注明 chunk 文件名，可在 `08-exported-scripts/files/` 下逐条复查。步骤 3 的
端点梳理仅用于发现域名，不构成静态分析证据。静态分析不执行任何页面代码，
`[验]` 均指**静态提取**，不是运行时行为验证。

---

## 2. 应用架构（全部 `[验]`，证据：`cdp-recon.txt` + bundle）

```
用户 → studio.tripo3d.ai (Cloudflare: challenge + Turnstile)
        ├─ SSR HTML（Nuxt 3，i18n prefix_except_default，10+ 语言）
        └─ 前端 bundle: tripo-webapp-assets.tripo3d.ai/studio-prod/_nuxt/*.js (112 chunk)
             ├─ api.tripo3d.ai/v2/studio/*          REST（51 路径，见 §3）
             ├─ msapi.tripo3d.ai/ms/web/api         微服务网关：POST + X-Micro-Method 头
             │     （gRPC 转码风格，如 /tripo.base.api.userapi.UserService/GetUserInfo）
             ├─ e-p.tripo3d.ai                       PostHog（phc_ 公钥、/e/ 上报、会话回放钩子）
             ├─ /cproxy/ws                           WebSocket（任务进度向）[推]
             ├─ tripo-public.tripo3d.ai              CMS 配置图/market-service slots + DCC 插件包
             ├─ tripo-data-public.rg1.data.tripo3d.com  模型/图预览数据（CloudFront 签名 URL）
             ├─ staticassets.tripo3d.ai / tripo-community-public.s3…  静态资源
             ├─ Firebase（项目 tripo-e3010）+ Google GSI 登录
             └─ 营销像素：GTM ×2、FB、TikTok、Reddit、Pinterest、Bing、Clarity、
                afi-b.com、yimg.jp、geddle.com、promotekit（联盟追踪）
```

要点：

- **首页由 CMS 驱动**：`msapi` 返回 `slotsByPosition`（`studio_home_gallery` 等
  slot，带 `templateKey`、`priority`、A/B `trackingParameter`）；画廊 banner
  直接指向 `/workspace/generate?tab=smart_mesh&utm_campaign=smart_mesh_p2_preview`
  （证据：`07-…capture.json` request-212 响应体）。
- **登录墙配置也走 CMS**：`api.tripo3d.ai/v2/studio/common/config?biz=login_wall`
  返回 4 个 variant（`Style-optimization-test1..3`）。
- **事件双轨**：PostHog（e-p）+ 自研 `trackingapi.TrackingService/ReportEvents`
  （msapi，批量上报，响应 `{"accepted":n}`）。bundle 里存在
  `session_replay`、`SessionReplayEventTriggerActivatedSession` 常量 `[验]`，
  PostHog 会话回放大概率开启 `[推]`。
- Cloudflare 对 headless 新 profile 直接 403+Turnstile（`04-…json`）；交互
  profile 通过后正常加载。这本身即是"反爬边界"的一手证据。

---

## 3. 功能清单（bundle 提取，`[验]`）

以下括号内为 bundle 原文 token（在 `08-exported-scripts/files/origins/ff8e9116…/studio-prod/_nuxt/` 内可直接 grep）。

### 3.1 生成操作（API 路径）

`/v2/studio/operation/` 下：`image_to_model`、`multiview_to_model`、
`text_to_model`、`batch_image_to_model`、`image-prompt-model`、
`meta_modification`、`symmetry_check`、`save_as_new`、`restore`、`cancel`、
`update_name`、`export`、`export-lite`、`export-batch`、`export-public-model`、
`download_with_name`、`quota`。

### 3.2 输入与图像工具

`/v2/studio/image/`：`gen_image_v2`、`re_gen_image`、`gen_multiview`、
`re_gen_multiview`、`split`、`upscale`、`available_templates`、
`get_image_asset`、`image_assets`、`batch_delete`。
图生模型侧支持图像自动修正开关（`enable_image_autofix`，默认 false `[验]`）。

### 3.3 网格工具（操作枚举）

- **重拓扑三分法**：`Retopology_Triangle`（三角）/ `Retopology_Quad`（四边）/
  `Retopology_SmartPoly`（智能多边形），各自独立计费（§4）。
- **Remesh**（`remesh`）、**网格填充**（`mesh_fill`）、**局部编辑**
  （`local_edit`、EditMesh 计费 50）、**魔法笔刷**（`MagicBrush`）。
- **AI 分割**（`ai_segmentation` / `segmentation`）、**部件生成**
  （`generate_parts` / `GenerateGenerateParts`）。
- **对称检查**（`symmetry_check`：传图判断是否对称 `[验]` 调用处为
  `body:{image:{bu…` 截断）。
- 拓扑类型选择（`model_topology_type`：`clean_topology` 等），首页 hero 的
  "干净拓扑"开关即在生成前选 Smart Mesh 路线 `[验]`（截图 + preset 代码）。

### 3.4 纹理

`texture_generation`、`apply_texture`、`texture_upscaler`（4K：`ImageUpscale4K`）、
`texture-pbr`（PBR 5 点）、`texture-edit`、**UV 编辑**（`UvEditGenerate` /
`UvEditRetry`，`smart-uv`）、**纹理风格**（`TextureStyle`）、
**delight**（去光照入材质）、质量档 `Detailed` / `Extreme`、
**8K**（bundle 常量 `tripo-texture-8k-new`、`unsupported_ultra_texture`）。
纹理对齐（`texture_alignment`：image / multiview `[验]`）。

### 3.5 绑定与动画

- 骨架类型（完整枚举，与开发者文档一致）：`biped`、`quadruped`、`hexapod`、
  `octopod`、`avian`、`serpentine`、`aquatic`、`others`。
- 操作：`rigging`（20 点）、`motion`（20 点）、`retarget`（枚举存在，
  studio 价目表未列价）、动画导出（`enable_bake_animation` 导出参数）、
  人形限定标记（`motion_humanoid_only`）。
- 付费墙插件名可见：`paywall_export_animation`、`paywall_multiview`（多视图
  为付费功能）、`paywall_smart_mesh(_multi)`、`paywall_smart_poly`、
  `paywall_uv_edit`、`paywall_segmentation`、`paywall_ai_completion`、
  `paywall_parts` 等，共 13 个 `[验]`。

### 3.6 导出与 DCC 桥

导出格式枚举（`{3MF:'3mf', FBX:'fbx', GLB:'gltf'/'glb2', OBJ:'obj',
STL:'stl', USD:'usdz'}`）+ 导出参数：`fbx_preset`、`texture_size`（默认 2K，
尺码含多档）、`texture_packaging`（zip）、`pack_uv`、`with_animation`、
`export_vertex_colors`、`bake_animation`。

**DCC Bridge 端口表（bundle 硬编码）**：

| DCC | key | 端口 | 插件包来源 |
|---|---|---|---|
| Blender | blender | 60600 | tripo-public.tripo3d.ai/plugins/blender-bridge/… |
| Unity | unity | 60610 | …/unity-bridge/… |
| Unreal | unreal | 60620 | …/ue-bridge/… |
| 3ds Max | 3ds_max | 60630 | …/3dsMax-bridge/… |
| Maya | maya | 60640 | …/maya-bridge/… |
| Godot | godot | 60650 | …/godot-bridge/… |
| Cocos | cocos | 60660 | …/cocos-bridge/… |
| MetaTailor | metatailor | 60680 | 外部网站 |
| Roblox | roblox | 60690 | …/roblox-bridge/… |

DCC 侧还有面数硬限制的 toast：Roblox `polygon_limit`、SketchUp `face_limit` `[验]`。

### 3.7 工作台 / 画廊 / 社区 / 账户

- 路由面：`/workspace/generate`、`/workspace/generate-image`、`/projects`、
  `/zh/assets`、`/zh/3d-model-gallery(/search)`、`/zh/creator-growth`、
  `/zh/events`、`/zh/education/*`、`/zh/billing`、`/zh/cli`、`/zh/layover`、
  `/zh/referral`、`/zh/discord-verify`、`/zh/profile`。
- 画廊用例筛选枚举：`all / featured / 3d_printing / character / vehicle /
  animal / architecture / furniture / props / weapon / clothing / classic /
  food / nature / …`（截图与 accessibility 一致）。
- **使用场景预设**（生成参数默认集）：`animation`、`interior_architecture`、
  `product`、`fashion`、`gaming`、`industrial`、`interior_design`、`other`、
  `3d_printing`、`vr_xr_ar`，每个场景映射 `default_01/02/03` 三套默认值
  （face_limit、texture、pbr、quad 等）。**默认 face_limit = 2 000 000，
  lowPoly 预设 = 5 000** `[验]`。
- 消息中心（`/v2/studio/message/*`）、交易记录（`txn/records`、
  `txn/team/records`、团队席位）、推荐/积分、反馈（`user/feedback`）、
  问卷（`user/survey*`）、临时存储 Token（`storage/temporary_token`）。
- **CLI 推广**：首页 banner"用 Tripo CLI 开始创造——Studio 订阅用户专享
  1000 API 积分"（截图为证）；`/zh/cli` 路由存在。CLI 与 MCP/API 走同一账号体系。

### 3.8 Agentic Canvas（forge3d）—— 门控新功能 `[验]`＋`[推]`

bundle 内存在一整套 **懒加载 chunk 家族**：`forge3d`、`forge3d-core`、
`forge3d-canvas`、`forge3d-auth`、`forge3d-entry`（含独立 CSS）。
- 入口按钮：header "Create in Canvas" / `agentic_canvas`（导航项里被过滤，
  需 `canvasAllowed`），feature flag `featureForge3dEntry.entry.agenticCanvas`
  / `createInCanvas`。
- 准入：`POST /tripo.canvas.api.agent.AccessService/GetAccess`（msapi），
  返回 `allowed: boolean`；常量 `smart_mesh_v2` 与它相邻 `[验]`。
- 中文日志串 `[forge3d-entry] Canvas 入口已读标记存储不可用`。
- Surface 内部功能未抓到（懒加载 + 未登录）→ `[未知]`。
- `[推]`：结合命名（agentic canvas + agent access service + canvas capture），
  这是 Tripo 的"AI 代理在 3D 画布上工作"入口，处于 allowlist 灰度阶段。

---

## 4. Credits 价目表（bundle 完整提取 `[验]`）

`{AICompletion:0, Completion:5, EditMesh:50, Export:5, FLUX_1_pro:10,
GenerateBase:15, GenerateBaseNexus:35, GenerateBaseNexusV2:100,
GenerateGenerateParts:30, GenerateGeometryQualityDetailed:15,
GenerateQuad:5, GenerateSmartPoly:20, GenerateTextureQualityDetailed:10,
GenerateTextureQualityExtreme:20, GenerateWithTexture:25, GPT_4o:10,
GPT_image_2:20, GPT_image_2_5:20, HomeImageToModel:40, HomeTextToModel:40,
ImageUpscale4K:10, MagicBrush:5, Midjourney:10, Motion:20, NanoBanana:10,
NanoBanana_2:10, NanoBanana_pro:20, PBR:5, ProjectCopy:5, QuickCap:0,
Retopology_Quad:10, Retopology_SmartPoly:30, Retopology_Triangle:5,
Rigging:20, Segmentation:40, TextureGeneration:10,
TextureQualityDetailed:10, TextureQualityExtreme:20, TextureStyle:5,
Upscaler:10, UpscalerExtreme:20, UvEditGenerate:20, UvEditRetry:10}`

观察（用于校准 parity 文档的成本对照）：

1. **Segmentation=40 是单步最贵的常规操作**（不含 EditMesh=50 与
   NexusV2 生成 100）——印证"语义分割是硬骨头"，与 OpenFigura 实测
   `segment` 只出噪声块互相印证（见 parity 文档 §9 补记）。
2. 一条典型链条：GenerateBase 15 + Segmentation 40 + Retopo_Quad 10 +
   TextureGeneration 10 + PBR 5 + Rigging 20 + Export 5 ≈ **105 点**，
   与 parity 文档"粗算 100+"一致，现在有价目表逐项支撑。
3. 绑骨：studio 20 点 vs 开发者 API 25 点——**两套账**（上一篇已疑，
   本次确认 studio 侧独立价目）。重定向 studio 未定价。

---

## 5. 模型版本表（bundle 枚举 `[验]`）

`v1.0-20240301`、`v2.0-20250506`、`v2.5-20250123`、`v2.5-20260210`、
`v3.0-20250812`、`v3.0-20260909`、`v3.1-20260211`、
`Nexus-v1.0-20260214`、`Nexus-v2.0-20260801`。

- `Nexus` 系列仅出现在 Smart Mesh 相关路径（`GenerateBaseNexus` 35 点、
  `GenerateBaseNexusV2` 100 点，后者带 `smartMeshP2Trial` 试用计数）。
  `[推]`：Nexus-v2.0-20260801 即对外口径的 P2.0 四边为主模型，在 studio 里
  以 "Smart Mesh" 形态分发（P2 preview banner 指向 `tab=smart_mesh`）。
  注意仍无独立四边拓扑验证 → 维持 parity 文档 §6 口径。
- `v3.1-20260211` 是当前默认（默认参数集 `model_version: se.v3_1`）。

---

## 6. 前端工程细节（供借鉴，`[验]`）

- **Nuxt 3 + 路由化 chunk**：pricing / user-management / community-growth /
  onboard / mobile-flow / tags-seo / forge3d-* 等一页面一 chunk。
- **状态常量散落的 localStorage/会话键**（前缀 `tripo-`）：导出设置、
  生成图像设置、模型操作、邀请码、多个 guide 已读标记、smart-mesh 设置
  （`tripo-smart-mesh-model-settings-v1`）、消息中心徽标等；会话键
  `_cfPre_tabId`（Cloudflare）。这类"设置持久化键"做法对 OpenFigura 的
  workbench（v0.4）有参考价值：**UI 状态与账本分离**。
- H.265/编解码无关；但注意 `streamNetworkBody:true` 实验开关与
  `canvasCapture={resolutionScale:.6}` 都是按日期切的条件编译常量
  （`2026-xx-xx > e || …`）——**功能按日期渐进放量**的写法值得学：
  OpenFigura 的预览/实验功能也可以用同样方式做可复算的灰度。
- 完整 i18n：`prefix_except_default`，en 默认 + zh/ja/ko/es/fr/de/it/pt/ru/tr。

---

## 7. 对既有 parity 文档的修正与确认

| 点位 | 2026-10-07 文档说法 | 本次实测 |
|---|---|---|
| P2.0 的落地形态 | 仅公开报道 | `[验]` studio 内 = Smart Mesh（`tab=smart_mesh`，campaign `smart_mesh_p2_preview`），模型 id `Nexus-v2.0-20260801`，100 点/次 |
| 绑骨点数 | API 文档 25 点 | `[验]` studio 侧 Rigging=20，两套账并存 |
| 蒙皮权重 | API 有 rig+skin | Bundle 只见 rigging/motion 操作枚举，未见独立 skin 补价 → 蒙皮包含在 rigging 内 `[推]` |
| 重拓扑 | 未提 studio 形态 | `[验]` 三分法独立计价：三角 5 / 四边 10 / SmartPoly 30 |
| 骨骼类型 | API 文档 7 类 | `[验]` bundle 完全一致 + `others` 兜底 |
| 导出格式 | GLB/GLTF/FBX/OBJ/USD/USDZ/STL/3MF | `[验]` 全部存在（`glb/gltf`、`fbx`、`obj`、`stl`、`usdz`、`3mf`），且有 DCC 预设与二次参数 |
| 免费档条款 | 403 未读到原文 | 本次同样只拿到登录墙配置，**条款原文仍未读**，维持原声明 |
| 新发现 | — | Agentic Canvas（§3.8）、对称检查 API、使用场景预设、CMS slot 系统、会话回放遥测 |

---

## 8. 可以借鉴什么（对着 OpenFigura 现有动词逐条过）

原则沿用仓库口径：只借**结构**（动词、参数、账本、契约），不借品牌与界面文案；
每一项都标注落到哪个现有动词/契约上，以及为什么。

### 8.1 立刻可做（低成本、高感知）

1. **`export` 参数补齐：FBX 预设 + 顶点色 + 纹理打包 + pack_uv**
   Tripo 导出面板支持 `fbx_preset`（Blender/Unity/Unreal/3dsMax/Maya/Godot/
   Cocos/Roblox/MetaTailor 分别的坐标与绑定约定）、`export_vertex_colors`、
   `texture_packaging: zip`、`pack_uv`。OpenFigura 已有 `export --format fbx`
   实测通过（见 PROGRESS 2026-10-08），补 preset 是把"能导出"变成
   "导到目标引擎不返工"。**落点：`export` 动词 + `export --format` 参数表，
   回归用 Blender 重新导入拍平验证。**
2. **使用场景预设（use-case presets）**
   `gaming/animation/3d_printing/fashion/…` → 面数/纹理/PBR/拓扑默认集。
   这正是 OpenFigura `StyleSpec`/asset-workflow 想做的事，但我们是"风格"，
   缺"**用途**"维度。**落点：`StyleSpec` 增加 `use_case` 字段（枚举照抄
   公开语义），预置参数表在 `capabilities().notes` 里声明来源。**
3. **对称检查（`symmetry_check`）**
   Tripo 把"输入图是否左右对称"做成独立 API——因为对称性决定镜像建模/
   镜像生成可行性。OpenFigura 的 `preflight` 是输入质量门禁，天然该有这一项。
   **落点：`preflight` 增加 `symmetry` 段（BiRefNet 抠图后求左右 IoU /
   翻折距离，给出 pass/flag，不阻断）。** 注意：Tripo 的实现细节未知，
   我们按自己的证据标准做，不照抄阈值。
4. **默认值表**：`face_limit` 默认 200 万、lowpoly 预设 5000——与我们
   `retopo`/`optimize` 的默认 ratio 可以对齐语义（**每场景一个面数预算**
   而不是全局 ratio）。**落点：`retopo`/`optimize` 接受 `--faces` 目标值
   （已经是 B 类第 9 项，本次给出了 Tripo 的实际默认锚点）。**

### 8.2 值得跟进（中成本，与路线图挂钩）

5. **Smart Mesh/quad 的进化路线**：Tripo 用独立模型（Nexus）做四边为主
   拓扑，且**用 30 点的 Retopology_SmartPoly 在服务侧兜底**——说明商业侧
   也承认"纯算法重拓扑不够"。我们的 QuadriFlow 已如实 CANCELLED
   （PROGRESS 2026-10-08），维持"不追原生四边"的判断；但可以把
   **SmartPoly 的计费位置**写进 parity 文档对外材料：四边能力他们也是
   付费的、模型级的，不是免费算法。
6. **UV 编辑的交互闭环**（`UvEditGenerate/Retry` = 20/10 点）
   印证 UV 精修值得付费。OpenFigura `uv` 已有 Smart Project；可把
   "UV 局部重开 + 保持纹理重新投影"列入 v0.3 的 `uv` 第二半。
   注意 `smart-uv` token 证明 Tripo 的 Smart UV 也是算法+人工触发混合。
7. **分割 40 点**：继续支撑 PartCrafter/HoloPart 学习式后端的必要性，
   并给出对外说法："语义分割是全行业最贵的一步，我们选了开源的
   PartCrafter 路线并在适配器里拒绝退化输出"（parity §4 已排期）。
8. **纹理由 4K→8K 的档位**（`ImageUpscale4K` 10 点、
   `texture-upscale`、`tripo-texture-8k-new` 常量）
   维持 v0.4 之后再看；先证明 4K 有意义（parity 已写）。
9. **CLI 与订阅绑定的推广策略**：Tripo 用"订阅送 1000 API 积分"推 CLI——
   说明 CLI 是他们的获客/留存面。OpenFigura 的杀手叙事正相反
   （CLI 就是全部产品）；写对外材料时可以直接引用这个对照。

### 8.3 保持观望（结构信号，暂不动手）

10. **Agentic Canvas**：agent + 画布 + 门控灰度。OpenFigura 的架构选择是
    "MCP 工具层 + 用户自己的 agent"，**不建画布**（不做 UI 是现行路线）。
    但它的存在证明了大厂的"agent 操作 3D 场景"方向；我们的等价物是
    `figura_*` 契约 + workflow 阶段账本。**行动：只在 README/产品页
    当作方向佐证引用，不排期。**
11. **CMS slot / A/B / 实验基建**：与本仓库"无遥测、无服务器"承诺冲突，
    不借鉴。唯一可用的是"**功能按日期条件放量**"的前端写法（§6），
    用于将来 localhost UI 的实验开关。

### 8.4 明确不学

- Credits 计费与付费墙矩阵（我们免费、本地、无配额）。
- PostHog 会话回放 + 11 个营销像素（与隐私承诺直接冲突，
  反而可以写进对比材料：Tripo 首页即加载会话回放钩子 `[验]`）。
- 9 个 DCC 插件矩阵（parity D 类已判）：我们的替代是文件 + 一个
  Blender 校验路径，继续保持。
- 云队列/并发/秒出——既有 non-goal，不动。

---

## 9. 未验证与限制（如实声明）

1. **登录墙后的运行时行为全部未验证**：生成、分割、绑骨、逐帧导出、
   Agentic Canvas 的实际效果，本文一律没有断言。所有 `[验]` 均为
   **静态提取**（bundle 字符串/结构）或**未登录页面实测**。
2. 场景抓包时页面是**未登录首页**：`/v2/studio/progress`、`/cproxy/ws`
   的运行时形态是 `[推]` 标注的推断。
3. 条款原文（免费档商用限制 §5.2.1 等）**本次仍未读到**——`studio.tripo3d.com/terms.html`
   需要登录态或反爬绕过，本方法论不做绕过。
4. 静态 bundle 是滚动发布的快照：chunk 名带内容哈希，本文 token 引用
   绑定 `08-exported-scripts/manifest.json` 的 SHA-256 `ec5370f6…`，
   复核对不上属正常（对方在发版）。
5. 指标计算（如 112 chunk、51 路径）的提取用 grep/正则，可能漏掉
   高度混淆的拼接字符串（例如 API 前缀与路径分开拼接的调用），
   以"至少这么多"读。

---

## 10. 证据文件索引

目录：`~/Desktop/OpenFigura/.local/runs/2026-10-16-tripo-studio-review/`（gitignored）。

| 文件 | 说明 | SHA-256 前 16 |
|---|---|---|
| `01-inspect-page.json` | 被动页面检查（DOM/a11y/存储键） | `6e9a7f53a1582ec6` |
| `03-scenario-launch.json` / `04-scenario-capture.json` | headless 被 Cloudflare 403 的证据 | `0af05cbf…` |
| `cdp-recon.mjs` / `cdp-recon.txt` | 源清单侦察（23 origins / 119 scripts） | — |
| `06-scenario-connect.json` / `07-scenario-connect-capture.json` | connect 模式全量（295 请求、含响应体、295 network-content） | `79c57ed9…` |
| `08-exported-scripts/`（manifest） | 142 脚本导出 + 逐文件摘要 | `ec5370f6…` |
| `09-js-app-analysis.json` | 静态代码结构分析（240 MB） | `a571cc23…` |
| `10-studio-home.png` | 未登录首页截图（hero + 画廊 + CLI banner） | `9e837a50…` |

复跑注意：旧版工具（6.5.0）缺少采集预算参数；全量记录步骤需要用较新的
本地构建（构建步骤见工具自身文档），其余步骤旧版即可。Chrome 需交互 profile 过 Cloudflare，headless 会 403。

---

## 11. 待办（需要人类拍板）

- [x] 8.1-1/2/3 三项（导出预设、use_case、对称检查）是否进 v0.3 排期？ →
      **已拍板并落地**，见 §12。
- [x] `use_case` 枚举要不要直接把 Tripo 的 10 个值照抄，还是收敛成
      OpenFigura 自己的 5 个？ → **收敛成 6 个**（game / animation / print /
      vr_ar / product_display / general），见 §12。
- [ ] 本文是否并入对外材料（公开资料调研的方法论本身可公开；**注意不再公开任何登录态数据——本文没有**）。

---

## 12. 落地记录（当日回填，2026-10-16）

手册 §8.1 四项已全部实现并有真实运行证据；证据根目录
`.local/runs/2026-10-16-borrow-batch/`，全仓 **630 测试通过**。

1. **导出预设（§8.1-1）**：`core/export_presets.py` +
   `openfigura export --format fbx --fbx-preset blender|godot|unity|unreal`，
   manifest 记录解析后的 exporter 参数与逐预设的验证状态。验证：
   Blender 5.2.2 元数据往返 + **Godot 4.7.2 实测**（godot 预设 FBX 的 AABB
   与 GLB 对照完全一致，delta 0.0；负对照轴向置换、match=false）。
   unity/unreal 标 `convention-only`，报告里如实说"未在本机验证"。
   **过程中实测抓到一个真 bug**：最初把 unity/godot 标成
   `global_scale=100 + CUSTOM`，Godot 实测发现 `bake_space_transform=True`
   已经完成米→厘米转换，×100 会双重放大——最终参数表以实测为准
   （marker 探针矩阵见 `godot-check2/`、`/tmp/godot-marker/`）。
   未做：顶点色开关（Blender 5.2.2 的 FBX 导出器没有该 RNA 属性，
   不能假装有）、贴图打包（FBX 已 embed、OBJ/USD 已落 textures/，现状即
   最优）、导出级 `pack_uv`（属 mesh 操作，留给 `mesh uv` 路线）。
2. **对称检查（§8.1-2）**：`core/symmetry.py`（stdlib PNG alpha 解码 +
   镜像 IoU），接入 `preflight` 输出新增 `symmetry` 段。JPEG/无 alpha/
   >8MP 一律 `unavailable` 并给原因。真实图：dark-knight matte 2492²
   1.12s 测得 roughly-symmetric 0.9424；xiaoman-front 2464² 2.07s 测得
   asymmetric 0.8784 并触发 advisory warning。阈值是 OpenFigura 自定
   启发式并在模块 docstring 声明。
   **修正**：§8.1-2 当时写"落点：StyleSpec 增加 use_case 字段"是把
   像素艺术 StyleSpec 和 3D 用途混为一谈，实际落点是 preflight（对称）
   与 presets（use_case），本记录为准。
3. **use_case 预设（§8.1-3）**：`core/presets.py` 6 个枚举值，每项带
   `basis`（只有 animation=50k 是 `vendor-claim`，锚定 Tripo 公开发布的
   三角 ≤50k；其余明确标 `openfigura-recommendation`）；`presets` /
   `figura_presets` 只读动词；`mesh --use-case` 仅在调用者未给
   `target_faces`/`ratio` 时填充，解析结果**记账**（ledger 里能看到
   值、来源 basis、源面数）。
4. **面数预算贯通（§8.1-4）**：真实运行——bunny 30,000 三角，
   `mesh optimize --use-case game` → 计算 ratio 0.666667 → 产出**恰好
   20,000 三角**（2.14s）；`mesh retopo --use-case game` → target_faces=
   20,000 真实传入管线，QuadriFlow 仍如实 CANCELLED、保留水密结果
   （70,024 三角、UV 被替换、requires rebake）——预算语法可用与
   "可动画级四边布线未达标"这两件事同时为真，继续按 §6 口径对外。

对 §9 未验证声明的更新：本节的 Godot 数值是**本机实测**；Unity/Unreal
导入仍是文档约定，不因为新增 preset 而改变证据强度。

---

## 13. 全量包深挖（同日续，2026-10-16）

第一轮只拿到页面实际触发的 112 个 chunk，Agentic Canvas 整块是 `[未知]`。
本轮把 **entry chunk 的懒加载闭包全部补齐**（公开 CDN 静态资源，250 个
chunk、11 MB，逐文件 sha256 在 `fetch-log.tsv`），并抓到运行时的
**zh 全量 UI 字符串表**（`_i18n/390d3dfa/zh/messages.json`，3964 条
key→en/zh，落成 `ui-strings-full.tsv`）。证据目录：
`.local/runs/2026-10-16-tripo-studio-review/11-full-bundle/`。以下全部
`[验]`（静态提取；登录墙后的运行时行为仍未验证）。

### 13.1 Agentic Canvas 全景（修正 §3.8 的 `[未知]`）

**它是一个「节点图画布 + 对话式 Agent」的混合工作台**，内部代号
forge3d，Agent 名为 **GPT·Astra**：

- **画布节点目录**（`featureForge3dCore.schema.*`，词条即节点类型）：
  `upload`（图片/3D 输入）、`generateImage`（概念图）、`generateHdModel`
  （"将一张参考图或四张标注视角图转 HD 模型"）、`generateSmModel`
  （图→Smart Mesh 轻量网格）、`multiview`（一图→前/后/左/右四视图）、
  `imagePrompt`、`partsDetect`（检测部件并逐件提取为图片+提示词）、
  `semanticSplit`、`cutout`（拼图切单张）、`segmentation`、`retopology`、
  `smartUv`、`texture`、`pbr`、`rigging`、`review`（**Approval gate，人工
  确认节点**）、`section`（分组）、`lab`（AI 3D Lab 节点）。
- **节点内参数**（同一命名空间）：拓扑 Quad/Triangle、面数 Polycount、
  模型版本档位（`v2.5 · Legacy` / `v3.0 · Fast & Balanced` /
  `v3.1 · Best Quality`、`Smart Low Poly v2`）、部件粒度三档
  （Simple 3-6 / Balanced 6-15 / Detailed 15+ parts）、纹理
  质量/分辨率/对齐、骨骼类型（biped/quadruped/hexapod/octopod/avian/
  serpentine/aquatic 的中英标签全在）。
- **Astra 会话协议**（msapi RPC + SSE，`featureForge3dAgent.*`）：
  Session（CreateSession/CreateTurn/ListTurns/UpdateSession/
  **BindAstraCard**）、Run（CreateRun/GetRun/StopRun/ListCanvasRuns）、
  Canvas（GetCanvas/SaveCanvas/**SubscribeAgentEvents**）、Node
  （ListNodesAssets/SelectNodeAsset/GetNodeAssetDetail）、Asset
  （ImportInputAssets/BatchGetInputAssets）、Project/Template/Tool 各一组。
  事件流是 `Accept: text/event-stream` + `X-Micro-Method` 的 SSE；
  事件类型：`plan-steps`、`request_user_select`、`astra_card`、
  `finish`、`error`（`fail_code` 如 `card_pending`）。
- **交互模式**：Agent mode 有 `Auto`（减少确认，自动继续）/ `Control`
  （关键步骤先审核）两档；消息面板有附件上限、快捷开始、运行状态
  （queued/running/failed/cancelled/completed）、"卡片未回答不许发新指令"
  的挂起协议、预计积分消耗提示（`estimatedCredits`）。
- **模板系统**：TemplateService 全族（ListTemplates/CreateTemplate/
  GetSourceTemplate/GetTemplateAssetDetail…）+ ProjectService
  `CreateProjectFromTemplate`；入口按钮文案 "Create in Canvas" /
  "Create New Canvas"。
- **AI 3D Lab 面板定位**（zh 原文）："检查和编辑资产、修复几何或纹理，
  或创建新内容。描述你想处理的内容。" ——**编辑/修复向**，不是纯生成。

对我们的意义（§8 原有判断强化）：**不建画布**这条线不变；但值得抄的是
三件工程实践：① `review` 审批节点 = 我们"visual_approval 归人类"的
图内表达；② `plan-steps` 事件 = 把 agent 计划显式流式暴露；③ 每个节点
= 一个可重跑步骤 + 参数快照，与我们 workflow 阶段账本同构。这些全部
可以只落在 `figura_*` 契约与文档表述，不需要 UI。

### 13.2 工作台工具的实测限制与档位（新增数值，全部 `[验]`）

| 能力 | 实测细节 |
|---|---|
| Smart UV | **硬限 三角 ≤ 80,000 / 四边 ≤ 40,000**；多部件（分割后）模型不支持；使用会移除现有贴图；提供 UV 利用率指标；重试计费（UvEditGenerate 20/UvEditRetry 10） |
| 绑骨 | 前置检查 `pre_rig_check`：不适合人形→提示先出 T-Pose 图（`generate_t_pose`）；面数超限→引导先重拓扑；有 "Try Rigging Anyway" 强制通道 |
| 分割 | 三种模式：Auto Segment（**基于几何+语义，无预览**）、Smart Segment（有预览）、Complete Mode（**部件补全** Part Completion）；拆分精度档；新功能试用计数 `Segment Trial x{count}` |
| 纹理 | `texture_model` / `retexture_generate+apply` / `texture_upscaler` / `pbr_generate` 独立端点；8K 为 Max 档权益（"Unlimited Access to 8K Textures"） |
| 动画 | `motion/*` 一整套后端：generate/get_task/get_asset/list_assets/rename_asset/list_active_tasks（**动作库**）；UI 三种入口：Text to Motion、**Video to Motion**、Multi-stage Motion（多关键帧，每帧一句 prompt，生成后 Apply 到模型，自动存动作库） |
| Pro Refine | 独立付费精修产品线：`pro_refine/create|history|free_times`，Max 档送 3 次免费 |
| 重试/回滚 | `operation/free-retry/`、`remove_retarget`、`operation/restore`；计划档位控制免费重试/历史（Free 1 天历史，Pro 7 天，Max 永久） |
| 会员并发/批量 | 档位实测：并发 1 / 10 / 100；批量导出 30 模型/批；队列优先级 基础/高/专属 |

### 13.3 端点补齐

`/v2/studio/*` 从 51 条扩到 **117 条**（`v2-endpoints-full.txt`），新增
motion 族、pro_refine 族、team 族（席位/邀请/升级全生命周期）、
wm-billing 族（订阅/续费挽回/portal）、`operation/` 下 rigging_model、
pre_rig_check、retarget_model、uv_edit/、retexture 族、import_user_model、
ai_completion、mesh_fill、local_edit、modification 等。msapi RPC 方法表
从 9 个扩到 **80 个**（canvas.agent 全族 + community + marketing event +
mosaic + sale coupon + trade cdk/invoice + user_lifecycle slots）。

### 13.4 三方对照：对本仓库的剔除结论（本次深挖后）

把 Tripo 功能按"对 OpenFigura 是否值得做"重排，**明确剔除**的项现在有
实测依据（不是口味问题）：

**正式剔除（Reject，写入路线图不再讨论）**
1. 对话式 Agent 面板 / Astra / 卡片协议 —— 这是 UI 层的会话产品；我们的
   对应物是用户的 Codex/opencode 自己 + `figura_*` 工具。**不做**。
   但 `plan-steps`/`review` 的**语义**已由我们的 workflow 阶段账本 +
   visual_approval 覆盖，无需新代码。
2. 画布节点编辑器（forge3d 全家）—— 同上，UI 非目标。**不做**。
3. Pro Refine 独立付费线 —— 阿里云/服务商精修属云服务，违背"本地、
   素材不出机"底线。**不做**。
4. 动作库云端资产（motion/list_assets 等）—— 本地文件即资产库，
   workflow/AssetRef 已覆盖。**不做**。
5. Video to Motion（视频动捕）—— 需要视频模型与 GPU 服务；本地等价物是
   MocapAnything 路线（已在看板上），Tripo 这套不借鉴。
6. 会话回放/营销像素/8 个广告像素（§8.4 已列）—— 与隐私承诺冲突。

**值得借鉴但降级为"补参数/补检查"（不新增动词）**
7. Smart UV 的 **80k/40k 硬限**是很好的对照锚：我们的 `mesh uv` 应把
   atlas 尺寸与面数上限写进 capabilities notes（低成本）。
8. 绑骨前置检查（T-Pose 建议、面数超限拦截）——我们的 `preflight`/
   `calibrated-rigging` 已有部分；可在文档写明与 Tripo 同序的门（先
   retopo → 再 rig）。
9. 分割的 Auto/Smart/Complete 三模式命名与"补全"概念：Complete Mode
   （部件补全）是我们 PartCrafter 适配器路线没覆盖的子能力，记录为
   watch（暂不做）。
10. 部件粒度三档（3-6 / 6-15 / 15+）—— 给 PartCrafter/HoloPart 适配器
    一个参数设计参考，记录，不排期。

**升级为"值得做"（新增候选）**
11. `operation/free-retry/` 与 `remove_retarget` 背后的产品观：**可撤销的
    步骤**。我们的对应物是 workflow 的 cancel/resume + 候选隔离
    （`_quarantine_candidate`）已实现；但"命名一个明确的重试动词"没有。
    候选：v0.3 之前不加动词，写进 usage 即可（低优先）。
12. Multi-stage Motion 的"每关键帧一句 prompt"接口形态：如果未来接
    本地 motion 后端（UniMate 已接），这是 prompt 交互的参考设计；
    记录，不排期。

**照旧不做/不碰**：Credits 计费矩阵（§4 表仍作对照素材）、DCC 插件矩阵、
云端并发、CMS/A-B 基建、会话回放。
