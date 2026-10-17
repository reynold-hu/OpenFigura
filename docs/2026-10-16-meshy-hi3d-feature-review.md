# Meshy AI / Hi3D 公开功能与算法调研 — 2026-10-16

> **定位**：OpenFigura 是独立开源项目（AGPL-3.0），目标与这些商业产品
> 不同——本地运行、素材不出机器、每一步可复算。本文只整理**公开资料**
> （公开页面、公开文档、公开代码/权重），用于决定我们自研什么；不复制、
> 不复刻第三方产品，也不使用其未公开实现。

Tripo 调研的续篇。目标：整理 **Meshy AI（meshy.ai）** 与
**Hi3D（hi3d.ai，Math Magic / 造好物）** 的公开功能面、接口面、计费面，
并确认它们背后**可获得的 3D 建模算法**（有代码/论文的算算法，没有的写没有）。

标记沿用前文：`[验]` 本次实测/静态提取；`[厂]` 厂商自述；`[推]` 有限推断；
`[未知]` 明确未知。

证据目录：`.local/runs/2026-10-16-meshy-hi3d-review/`
（`meshy/` 与 `hi3d/` 各含 inspect、CDP 侦察、chunk 抓取日志、截图；
逐文件 sha256 在 `fetch-log.tsv`）。

---

## 0. 一句话结论

- **Meshy** 是三家里产品化最狠的：双阶段生成 + **Smart Topology（原生部件
  分离）**、8K 纹理、打印线（可打印性/修复/多色/自动拆件）、**Creative Lab
  实物商品线**、**AI Video**、**3D Agent（threads/canvas/skills）**、
  MCP（24 工具）+ CLI + App 全渠道。算法闭源，无公开论文。
- **Hi3D** 是**3D 打印优先**的垂直平台：Sparc3D（1024³ 稀疏表示）、浮雕、
  **智能拆件 + 连接件（榫卯/铆钉/插接/球关节）**、多色、刺绣、桌面 Agent
  （内置 "GPT-6 Astra"）、Maker Workshop 商品模板。**算法有公开论文
  （Sparc3D, arXiv 2505.14521），但代码被 Math Magic 闸门（"经批准后释放"）**。
- 对我们真正可拿的算法是 **Hi3DGen（MIT，正常图桥接）**——与 hi3d.ai 不是
  同一家，但它是可本地研究的开源高保真几何生成路线。
- **新的高价值借鉴项**：本地**可打印性检查**（analyze/repair）与**多色
  分件**、以及 Meshy 的 `--dry-run` 式**成本预估**交互。详见 §5。

---

## 1. 方法与证据链

### Meshy（`meshy/`）

1. Chrome 独立 profile + CDP `9223`，打开 `https://www.meshy.ai/`（重定向
   `/zh`）。公开页面只读检查：站点是 **Next.js（Turbopack）**，API 走
   同源 `/meshyd-api/web/*` 与独立的 `/agent-api`，静态资源在
   `cdn.meshy.ai/webapp-build-assets/production/_next/static/chunks/*`
   （`01-inspect.json`；`04-screenshot.json` / `home.png`）。
2. 场景化 attach 路径不可用（页面有 service worker）→ 改用直接 CDP
   做公开端点梳理（`cdp-recon.txt`，80 个 origin）。
3. **公开前端资源**：从页面记录提取 210 个 chunk URL，递归收集到 **343 个
   JS、123 MB**（`fetch_chunks.py` + `retry-log.tsv`；CDN 限流后用 curl 重试
   112 个全部成功；逐文件 sha256 在 `fetch-log.tsv`）。
4. **官方文档面**（`[厂]`，但接口契约以文档原文为准）：
   docs.meshy.ai 的 API/计费页、`/zh/features/3d-agent`、`/zh/mcp`、
   `/zh/cli`。文档与 bundle 的枚举相互印证（下文的 `[验]`/`[厂]` 分别标注）。

### Hi3D（`hi3d/`）

1. 同一 Chrome 新标签 `https://www.hi3d.ai/`（重定向 `/zh`）。Nuxt 3，
   公开静态资源在 `hitem3dstatic.zaohaowu.net`，API 同源 `/aigc/api/*`
   （`01-inspect.json`、`cdp-recon.txt`、`02-screenshot.json` / `home.png`）。
2. **i18n 全量**：`/_i18n/0_WQbECf/zh/messages.json` → `messages-zh.json`
   （845 KB，`en`+`zh`，5417/5436 条），平铺为 `ui-strings-full.tsv`。
3. **公开配置端点**（未登录可读，浏览器同款 GET）：
   `generate/config`（功能开关）、`template/config/list`（商品模板与积分
   定价）、`membership/marketing/activities`（Agent 上线活动）、
   `desktop/version/latest`（桌面客户端版本）。
4. **公开前端资源**：chunk 收集 **719 个 JS、17 MB**（`chunks/`、`fetch-log.tsv`；
   3 轮闭包后仍有 118 个未展开，见 §7 限制）。
5. 截图：`meshy/home.png`、`hi3d/home.png`。

---

## 2. Meshy 功能全景（除注明外 `[验]`）

### 2.1 平台形态

Next.js 商城站 + Web 工作台（`/workspace`）+ **桌面/移动 App** + **MCP
server**（`meshy-dev/meshy-mcp-server`，npm 本地 stdio，24 个工具，API key
Pro+）+ **CLI**（`meshy-dev/meshy-cli`，Node 22.12+，`meshy auth login`
浏览器 OAuth、`meshy make "prompt" -o x.glb`、`--dry-run` 预估积分、
`--json` 给 agent）+ **公开 REST API**（`api.meshy.ai/openapi/*`，Bearer
key）+ PostHog/Statsig/大量广告像素（会话回放类埋点存在 `[验]`）。

### 2.2 生成线

- **Text→3D（v2）**：两阶段 **preview（几何）→ refine（贴图）**，分开计费。
  模型：`meshy-6-lite / meshy-6 / meshy-7.1 / latest`；
  **`smart-topology`（`meshy-t2` / `meshy-t2.5`）**：三角面、可设
  `target_polycount`（t2: 100–15k，默认 4k；t2.5: 100–30k，默认 15k）、
  **原生分离部件**（"natively separated parts"）`[厂]`；
  `geometry_resolution: standard/2k/4k`（Ultra 面，+5 点）；
  `pose_mode: a-pose/t-pose`；**`auto_size`：AI 视觉估真实世界高度并缩放**
  （原点 bottom/center）；`target_formats` 只生成所需格式；`alpha_thumbnail`；
  `moderation`；8K 纹理（4K/8K 需 6/7.1）。
- **Image→3D / Multi-Image→3D**：同上参数；多图输入 2 张起。
- **图像线**：Text→Image / Image→Image（`nano-banana` 系列 / GPT Image）、
  `image-styles`、去背景、生成命名。
- **AI Video**（新产品线）：Text/Image→Video，模型目录含
  Kling 2.5 Turbo、Seedance 2.0/Fast、MiniMax H3、Gemini Omni Flash 1.1、
  Omni Flash 等，通过 fal.ai 等外部模型接入 `[验]`；时长 5/10/15s，按
  duration 计费（例：Seedance 2.0 5s=110 点）`[验]`。
- 版本枚举（bundle）：`Meshy-2/3/4/5/6/7/7.1`、`meshy-6-lite`、
  `meshy-5.1/5.3`、`meshy-3-turbo`、`meshy-t2/t2.5`、`meshy-3d-agent`。

### 2.3 后处理与角色线

- `remesh`、`resize`、`convert`、`uv-unwrap`、`retexture`（2K/4K/8K）。
- **Rigging**：类型 `biped / quadruped / quadruped-cat / smart(UniversalRig)`；
  API 价 5 点/次。
- **Animation**：动作库巨大（bundle 内数百条 mocap action：Archery_*、
  Backflip_*、Axe_*、Bass_Beats、bicep_curl…；含 `Walking_Woman`、`Idle_02/03`、
  `Forward*_Run_Fight` 等），API "up to 10 actions/req, 3 点/action"；
  另有 **Text→Motion**（`prime` 10 点 / `swift` 3 点）与 **custom-pose**
  功能页。
- **模型编辑**：`model-edit` 相关（bundle），页面列 "custom pose"。

### 2.4 3D 打印线（`[验]`+`[厂]`）

- API：`Analyze Printability`（免费）、`Repair Printability`（10 点）、
  `Multi-Color Print`（10 点）、`Auto Split`（10 点）、
  `tasks/{id}/printability|split-plan|multi-color-ai-optimize|part-segmentation`。
- **Creative Lab**（实物商品线，Beta）：Keychain / Fridge Magnet / Figure /
  Vinyl Figure / Brick Figure / Lamp / Keycap / Collapsible Fidget /
  Fidget Pixel；Prototype 6–30 点 + Build 6–50 点；免费档每日若干次；
  付费可下单**打印并邮寄**（9 国）`[厂]`。
- 打印插件矩阵：Bambu Studio、OrcaSlicer、Creality Print、Ultimaker Cura、
  Elegoo Slicer、Lychee；引擎/DCC：Unity、Unreal、Roblox Studio、3ds Max、
  Blender（`[厂]` 导航/集成页）。

### 2.5 3D Agent（`[验]` 接口 + `[厂]` 说明）

- 独立 `agent-api` 域 + `/v4/agent/*`：
  `threads`（turns/continue/cancel/evaluations/locate/share）、
  `projects`（canvas/stats）、`artifacts`（upload/register/batch/export）、
  `skills`（create/collect/delete/showcases）、`template-runs`、
  `ops/remove-background`、`preferences`、`pricing`、`usage`、
  `public/v4/agent/shared/{shareCode}`。
- 产品口径：**世界首个对话式 3D Agent**（Beta）——头脑风暴 → 批量 2D 概念 →
  选一个 → 3D → 可打印性检查/修复 → 导出；聊天免费、操作扣积分 `[厂]`。
- MCP 工具面（24 个）含 `meshy_text_to_3d`、`meshy_get_task_status`、
  `meshy_check_balance`、creative 多阶段工作流；资产落 `meshy_output/`；
  需 Pro+ API key `[厂]`。

### 2.6 计费（`[验]` bundle + `[厂]` docs）

**API credits**：3D 生成 mesh-only 5–20；带 2K 贴图 15–30；8K 35；
preview/refine 分开（refine 2K/4K 10、8K 15）；Ultra +5；
图像 3–12；rig 5；animation 3/action；text-to-motion 3/10；
remesh/uv 5；convert/resize 1；printability 免费、repair 10、multi-color 10、
auto-split 10；Creative Lab 见 §2.4。

**订阅档位（bundle 内表，credits/assets/tasks/retries）**：

| 档位 | credits | assets | tasks | retries | 备注 |
|---|---|---|---|---|---|
| Free | 100 | 10 | 1 | 0 | |
| Starter | 250 | 25 | 5 | 2 | 下载 20/社区 15 |
| Pro | 1000 | 100 | 10 | 4 | 无限下载 |
| Premium | 3000 | 300 | 30 | 12 | Creative Lab 免费设计 4 次 |
| Ultra | 8000 | 800 | 100 | 40 | Creative Lab 12 次 |
| Studio | 4000 | 400 | 60 | 24 | 团队席 1/3/5 → 5500/16800/28000 点 |
| Enterprise | 10000 | 1000 | 100 | 100 | |

---

## 3. Hi3D 功能全景（`[验]`+`[厂]`）

### 3.1 形态

Nuxt 站点 + **Hi3D Studio**（编辑/优化/打印准备）+ **Hi3D Agent 桌面客户端**
（Win/macOS，内置 "GPT-6 **Astra**"）+ Maker Workshop（商品化模板）+
公开 API（`/aigc/api/*`）+ **MCP 客户端授权流**
（`/aigc/api/auth/mcp/consent-context|consent-decision`，界面里有
"Configure Hi3D MCP in the current client (Codex or Claude Code)" 的引导）
+ 桌面版下载（`/desktop/version/latest`）。主体公司：**Math Magic（造好物）**。

### 3.2 功能清单（i18n 命名空间 + API 实证）

- **Image→3D**：Sparc3D（自研，见 §4.1），v3.0 主推；输出 glb/obj/stl。
- **Portrait Model**（人像）；**3D Relief（浮雕）**：2D→高精度浮雕，
  适配 3D 打印/CNC；生成时可选 **私有许可（可商用）或 CC BY 4.0**；
  支持照片/线稿/Logo/手绘，自动边缘与细节保留。
- **Model Segmentation**（分割）与 **Split-to-Print（智能拆件）**：
  自动拆头/躯干/四肢/武器/底座；**连接件**：榫卯、铆钉、插接、**球关节**；
  分件自动**封闭水密**；连接件类型/位置/方向/尺寸可在 Studio 调整；
  面向多色打印、拼装、**可动设计**。
- **Multi-Color**（分色打印）与 **material/color** 工具；
  **Embroidery（刺绣）** 开关与定价（`generate/config`: `isEmbroideryFree`,
  `embroideryPrice: 0`，原价 12）。
- **2D Image Editor**（`image-task/image-edit/*`，多视图配额、professions）、
  **Model Edit**（`generate/model-edit-record`、`user/part-edit-state`）、
  remesh、similar-pixels、texture（i18n `threeDRelief.explore.texture*`）。
- **Maker Workshop 模板**（`template/config/list`，8 个）：
  Perler Beads（拼豆，imageEdit 16 / model3d 0）、Realistic / Chibi /
  Occupation / Cartoon / Brick-style / Pet Figurine（imageEdit 10–16 /
  model3d 25）、Metal Fridge Magnet（10/10）；分类 Maker Items / Figurines；
  有 `displayPlacements`（`maker_workshop_hover`）商品位。
- **社区/活动**：contest/events（submissions、likes、winners）、showcases、
  教育计划、NPS、邀请。
- **Agent**（`hi3dAgent`）：对话式完成生成/修改/**拆件**/配色；**Skills**
  （输入 `$` 选择，如"浮雕收纳盒""可动人偶"）；模型文件在对话中 3D 预览；
  **部分能力需云端**（明确写"相关图片/模型/任务内容会发送至云端"）；
  计费：对话 Token 与功能调用统一折算为积分；桌面端目前不支持手动建模
  编辑（`[厂]` FAQ 原文）。
- **API 观察**：`generate/model3d/submit`、`studio/task/submit`、
  `image-task/img-edit`、`template/assets/*`、`pay-wall/quota`、
  `onboarding/*`、`user/tasks/task-center`（任务中心/行业选择问卷）、
  `share/models`（分享卡/视频）。
- 版本枚举：`sparc3`、`hi3d-3`/`hi3d-v3`/`hi3d-v21`（bundle）。

---

## 4. 算法面（用户点名的"算法，如果有的话"）

### 4.1 Sparc3D（Hi3D 背后的模型，`[验]` 论文 + 项目页）

- 论文：**arXiv 2505.14521**《Sparc3D: Sparse Representation and
  Construction for High-Resolution 3D Shapes Modeling》（NTU + **Math
  Magic** + Imperial；作者 Zhihao Li 等）。
- 方法（论文摘要原文要点）：**Sparcubes**——把原始网格通过
  **稀疏可变形 marching cubes** 表示成 **1024³** 表面（SDF + 变形场散射到
  稀疏 cube，可微优化，天然支持开放表面/多连通/复杂拓扑与**水密化**）；
  **Sparconv-VAE**——全稀疏卷积 VAE（+ Point Transformer v3 风格的局部
  注意力），模态一致、近无损重建；再接 latent diffusion 做高分辨率生成。
- **代码**：`github.com/lizhihao6/Sparc3D`，项目页明确写
  **"Code may be released upon the approval of Math Magic"**——即**未开源**
  （截至 2026-10-16）。Demo 在 HF Space。
- 对我们的意义：hi3d.ai 的"几何精度/可打印"优势有明确的技术解释
  （1024³ 稀疏 SDF 表示 vs 我们后端的面片级生成），但**算法代码拿不到**；
  可借的是**表示思路**（高分辨率稀疏 SDF + 可微提取 → 水密），
  实现需自研或用开源近似（见 4.3）。

### 4.2 Meshy 的算法面（`[验]` 无公开算法）

bundle 与官方文档里只有**产品参数**（模型代号 meshy-6/7.1、T2/T2.5
"smart-topology"、"native parts"、Ultra 2k/4k 几何、8K 纹理），**没有论文、
没有开源代码**；对外不披露架构 `[未知]`。可借鉴的只有产品设计（§5），
算法本身不构成可复现来源。

### 4.3 Hi3DGen（开源，MIT；与 hi3d.ai 不是同一家）

- 仓库：`Local/Opensource/Hi3DGen`（ByteDance/CUHK-Shenzhen，ICCV 2025，
  **MIT**），论文 arXiv 2503.22236。
- 管线（`hi3dgen/pipelines/hi3dgen.py` + `app.py` 实测阅读 `[验]`）：
  1) 输入图 → **BiRefNet** 抠图（`ZhengPeng7/BiRefNet`）；
  2) **正常图合成**：`Stable-X/trellis-normal-v0-1`（或
     `Stable-X/yoso-normal-v1-8-1`）先出高精度 normal map；
  3) **稀疏结构流**（sparse structure flow）→ 稀疏体素坐标；
  4) **结构化潜变量流**（structured latent flow，正常图条件）→ SLAT；
  5) `slat_decoder_mesh` 出网格（可选 radiance field 出外观）。
  即"**用法线作为中间桥接**"提升几何细节保真，网格从 **TRELLIS**
  微调而来（README 自述，并称受 Rodin/Tripo/Dora 启发）。
- 运行条件（requirements/README）：Python 3.10、`torch 2.4 + CUDA`、
  `spconv-cu*`、`xformers`——**CUDA-only，无 MPS/CPU 路径**；Mac 不可跑。
- 结论：这是**唯一可直接拿来当本地几何后端候选的开源算法**
  （与 MIA/UniMate 同级别的"CUDA 机器上跑"路线），不是 hi3d.ai 的算法。
  接入前按仓库既有规则：先验证 spconv/xformers、记录 normal 证据、
  校验法线图与归一化逆变换（与 `docs/2026-10-07-upstream-integration-rigging.md`
  的 Hi3DGen 条一致）。

---

## 5. 可借鉴 / 剔除（对 OpenFigura）

### 5.1 立刻可做（低成本、纯本地）

1. **本地可打印性检查 `print-check`（新候选动词，建议优先）**
   Meshy 把 printability 做成免费入口 + 修复收费；Hi3D 把"水密/可打印"
   当核心卖点。我们已有 inspect / mesh / pymeshlab 运行时：
   - 非流形边、开边、破面、零面积面、重复面（已有部分在 mesh report）
   - **最小壁厚**（射线/内切球近似）、**悬垂角**、**底部着地面积**、
     **包围盒 vs 打印平台**
   - 输出分级报告（pass/warn/fail）+ 修复建议，**不承诺自动修复**
   - 落点：新动词 `print-check`（CLI/MCP），或并入 `inspect --print`。
   这是本批调研里**性价比最高**的新能力：对手收费/当卖点的东西，我们在
   本机可以做到"检查"级别，且与现有 GLB 工具链同构。
2. **`--dry-run` 成本/步骤预估（CLI 交互）**
   Meshy CLI 的 `meshy make --dry-run` 打印"计划几步、约多少积分"再确认。
   我们无积分，但**计划步骤 + 预计耗时/面数/是否触发长任务**同样有用：
   `openfigura plan retopo+rig+export` 式预演，落点：workflow 提交前打印
   计划（只读，不执行）。
3. **多色/分色分件（`split-plan` / multi-color）**
   本地可行路径：按材质/顶点色聚类 + 连通分量拆分（Blender），产出
   分件 GLB + 装配说明；连接件（榫卯/球关节）属几何生成，成本更高，
   先做**分件与分色预览**，连接件列为 v0.4 候选。
4. **模型版本/预算参数对照表**（文档级）：Meshy T2/T2.5 的
   `target_polycount` 区间（15k/30k）与 Hi3D 的商品档位，补进
   `docs/mesh-optimization.md` 的预算参考（已有 use-case 预算表）。

### 5.2 值得跟进（需 GPU / 较大工程）

5. **高分辨率稀疏 SDF 表示（Sparc3D 思路，非代码）**：
   若未来自研/移植几何后端，目标应是"**水密 + 可打印**优先的表示"，
   而不是单纯提高面数；可先用 Hi3DGen 的 normal-bridging 作为开源近似。
6. **Hi3DGen 接入试验（CUDA）**：按既有 upstream-reuse 流程排期；
   与 MIA/UniMate 共用一台 CUDA 机器；产出需法线图与逆归一化证据。
7. **3D 浮雕（relief）**：本地需要深度/高度估计模型（如 Depth Anything
   类），属"新后端"而非本仓库自研；列为 watch，不在 v0.3。
8. **`auto_size`（AI 估真实尺寸）**：3D 打印非常实用；本地版可先做
   "按参考图人体比例/常见物体尺寸"的**启发式建议**（弱于 AI，不冒充）。

### 5.3 明确剔除（与隐私/产品边界冲突，或不属于工具层）

- Meshy **AI Video**、Creative Lab **实物下单/代印**、云端 Agent
  （threads/canvas）、积分/订阅/优惠券、会话回放与广告像素。
- Hi3D **电商/代印/Maker 商品线**、桌面客户端、云端 Agent、比赛社区、
  刺绣/浮雕的**云服务**形态（算法层面另议）。
- 两家都有的 **DCC/切片器插件矩阵**（Bambu/Orca/Cura/…）：继续走
  "文件 + 一个 Blender 验证路径"。
- **Sparc3D 本身**：代码未开源且带公司审批闸门，不引入、不使用其未公开权重。

---

## 6. 关键数字速查

- Meshy API：mesh 5–20；2K 15–30；4K 15–30；8K 20–35；Ultra +5；
  refine 10/15；rig 5；animation 3/action；text-to-motion 3/10；
  printability 0；repair/multi-color/split 各 10。
- Meshy 订阅：Free 100 点 → Enterprise 10000 点（表见 §2.6）；
  Studio 团队 1/3/5 席 = 5500/16800/28000 点。
- Meshy 能力上限：`target_polycount` 100–300,000（remesh）；T2 15k / T2.5 30k
  （原生拓扑）；8K 贴图；并发（档位）未在 bundle 明确，`[未知]`。
- Hi3D 模板：figurine 系 imageEdit 10–16 + model3d 25；拼豆 16 + 0；
  冰箱贴 10+10；免费档可用性逐模板标注。
- Hi3D 版本：Sparc3D v3.0（`hi3d-v3`）；桌面端与 MCP 授权流存在。

---

## 7. 未验证与限制

1. **未登录**：两家的生成运行时、真实速度、失败率、条款原文（含商用与
   免费档限制）都**没有**验证；本文所有功能以静态提取/公开文档为准。
2. Meshy 的场景化 attach 被 service worker 拒绝（工具契约行为，非站点
   故障）；改用直接 CDP 端点梳理 + 公开资源收集。
3. Meshy 公开资源首次收集被 CDN 限流（112 个失败已 curl 重试补齐）；Hi3D
   的收集做了 3 轮，仍有 **118 个引用未展开**（`fetch-log.tsv` 可查
   错误），所以 §3 的端点表是"至少这么多"，不是完整清单。
4. Meshy 的模型版本/参数来自 **官方 API 文档**（`[厂]`）与 bundle 交叉；
   文档会漂移（`lowpoly` 2026-10-30 退役等），引用前回原文。
5. Hi3DGen 未在本机运行（无 CUDA），算法结论来自**源码与论文阅读**；
   Sparc3D 结论来自**论文与项目页**，代码不可得。
6. 两站的 i18n 字符串表已落盘（`meshy` 为枚举+文档；`hi3d` 为
   `ui-strings-full.tsv` 5437 行），但**未做逐条人工审校**。

---

## 8. 证据文件索引

`~/Desktop/OpenFigura/.local/runs/2026-10-16-meshy-hi3d-review/`

| 路径 | 内容 |
|---|---|
| `meshy/01-inspect.json` | Meshy 首页被动检查（含网络/脚本/存储键） |
| `meshy/cdp-recon.txt` | 80 个 origin、脚本清单（含全部 chunk URL） |
| `meshy/chunk-urls.txt` / `chunks/` / `fetch-log.tsv` | 343 个 chunk、逐文件 sha256 |
| `meshy/home.png` | 未登录首页截图 |
| `hi3d/01-inspect.json` | Hi3D 首页被动检查 |
| `hi3d/cdp-recon.txt` | Hi3D origin/脚本清单 |
| `hi3d/messages-zh.json` / `ui-strings-full.tsv` | Hi3D 全量中英字符串（5437 行） |
| `hi3d/generate-config.json` / `template-config.json` / `desktop-version.json` | 公开配置端点原文 |
| `hi3d/chunks/`（719 个）/ `fetch-log.tsv` | Hi3D chunk 闭包与 sha256 |
| `hi3d/home.png` | 未登录首页截图 |
