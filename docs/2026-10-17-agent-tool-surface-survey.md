# Agent 工具面与 Skills 调研 — 2026-10-17

> **定位**：OpenFigura 是独立开源项目（AGPL-3.0），目标不同——本地、隐私、
> 可复算。本文只整理**公开仓库与公开文档**里的 agent 集成方式（工具粒度、
> 任务生命周期、安装与授权、skill 打包），用于改进我们自己的 MCP/CLI
> 体验；不复制对方实现。

证据：`.local/runs/2026-10-17-skills-survey/` 下的公开 README/INSTALL
原文（Meshy MCP server、meshy-cli、meshy-3d-agent、Hi3D i18n 的 MCP 文案）。
Meshy 数字与工具名来自其公开 README；Hi3D 来自公开页面 bundle 的
i18n 字符串；Tripo 的公开文档 sitemap 中未检索到 MCP/Agent/Skill 页面
（负向结果，不代表不存在）。

## 1. Meshy

### 1.1 MCP server（28 个工具）

公开 README 的分组（工具名原文）：

| 组 | 工具 |
|---|---|
| 3D 生成 | `text_to_3d`, `text_to_3d_refine`, `image_to_3d`, `multi_image_to_3d` |
| Creative Lab | `creative_lab`（9 种商品） |
| 后处理 | `remesh`, `retexture` |
| 绑定/动画 | `rig`, `animate`, `text_to_motion`, `list_animations` |
| 转换 | `convert`, `resize`, `uv_unwrap` |
| 图像 | `text_to_image`, `image_to_image` |
| 任务管理 | `get_task_status`, `list_tasks`, `cancel_task`, `download_model` |
| 工作区 | `list_models` |
| 3D 打印 | `send_to_slicer`, `analyze_printability`, `repair_printability`, `process_multicolor`, `auto_split` |
| 账户 | `check_balance`, `list_usage` |

值得学的设计（全部来自 README `[公开]`）：

- **生命周期动词统一**：每个资源都有 create / get / list / wait / stream /
  delete；`make` 只是把文档化流程串起来（preview→refine，或单张图→带贴图）。
- **重试语义写死**：创建请求在超时/5xx 后**绝不重发**，避免重复计费；状态
  查询按 API 建议间隔重试。
- **预算可见**：`check_balance`、`list_usage`、创建前 credit 估算；
  工具描述里直接写每档价格。
- **输出组织**：自动落 `meshy_output/` 项目文件夹 + 元数据 + 历史。
- **打印线成套**：可打印性分析（含水密/孔洞/非流形/退化/壁厚）→ 修复 →
  多色 3MF → 自动拆件（按部件/按颜色/带连接件）→ 本机切片器探测并返回
  启动命令（7 种切片器）。
- **任务类型分派**：`list_tasks` 默认列生成类，打印/绑定/动画/动作/后处理/
  Creative Lab 需显式 `task_types`；`list_models` 默认 image-to-3d。
- **安装**：`npx add-mcp` 自动写各客户端配置；也提供“让 agent 安装”的
  提示词；鉴权用环境变量 API key（Pro+）。

### 1.2 CLI（meshy-cli）

- OAuth 浏览器登录（`auth login`），CI 用 `MESHY_API_KEY`；`auth status`。
- `make`：一条命令串完流程，`--dry-run` 打印步骤与积分估算（不扣费）。
- 每个端点也是命令：`text-to-3d create|get|list|wait|stream|delete`；
  `meshy api GET /balance` 作为未建模端点的逃生口。
- 面向脚本/agent：stdout 只放结果，进度进 stderr；管道/agent 场景自动
  JSON，可固定 envelope；`doctor` 本地环境自检（无网络）。
- 设备码登录（headless）：打印链接 + 短码，用户任意设备批准；不要求把
  key 粘回终端。

### 1.3 Agent skills（meshy-3d-agent）

- 拆成两个 skill：`meshy-3d-generation`、`meshy-3d-printing`，各自带
  `references/` 目录；安装器按客户端自动放置（Claude Code、Codex、Cursor、
  Hermes、Gemini CLI、OpenClaw 等）。
- INSTALL.md 明确写给 agent：先查 Node 版本（22.12+），缺了就请用户装；
  不要求 API key；**不用 sudo**；`auth login --device` 后把链接和短码
  原样给用户，保持命令运行等待其自行退出；过期才重开一次；安装完成后
  用 `balance` 验证并汇报，再建议第一个请求。
- 这印证了 skill 的价值：**把“长任务、授权、验证、安全边界”写成流程**，
  而不是只列命令。

## 2. Hi3D

- MCP：**Streamable HTTP + OAuth**，名称 `hi3d`；页面给出的安装提示词要求
  agent 引导浏览器授权、验证连接、列出工具，并说明是否需要重启
  （`messages-zh.json` 的 `mcp.setupPrompt` 原文）。
- 桌面 Agent 内另有 `$` 触发的 **Skills**（如“浮雕收纳盒”“可动人偶”），
  每个 skill 新开一个独立对话；计费把对话 Token 与功能调用统一折算积分。
- 本次未找到公开的 Hi3D MCP server 仓库；其授权端点
  （`/aigc/api/auth/mcp/consent-context|consent-decision`）在公开 bundle 中
  可见 `[公开页面]`。

## 3. Tripo

- 公开文档 sitemap（105 KB）中未检索到 MCP/Agent/Skill 页面；官网也未见
  官方 MCP 文档。**负向结果**，不作“没有”的强断言。

## 4. 对照与我们的位置

| 维度 | Meshy | Hi3D | OpenFigura（现状） |
|---|---|---|---|
| 工具数 | 28（MCP） | 未公开（MCP + 桌面 skills） | **32 CLI / 32 MCP 镜像** |
| 任务模型 | create/get/wait/stream，创建不重发 | 对话 + `$` skills | 长任务阻塞式 `generate` + 持久 `workflow-*` 阶段账本 |
| 成本可见 | balance/usage/预估 | 积分折算 | 免费本地，无计费；有阶段账本与耗时 |
| 输出组织 | `meshy_output/` | 对话内预览/下载 | 任务目录 + `provenance.json` + `provenance`/交付清单 |
| 打印线 | 分析/修复/多色/拆件/切片器 | 拆件/连接件/多色/浮雕 | `print-check`（拓扑/尺寸/朝向 + 可选壁厚代理） |
| Skills | 两个 skill + references | 内置 `$` skills + MCP | **本批新增 `skills/openfigura/SKILL.md`** |
| 运行位置 | 云 | 云 + 桌面客户端 | **本机；CPU-first，无 GPU 也能完成核心闭环** |

我们的优势不需要模仿：本地/隐私、可复算账本、免费、CPU 可跑、工具面
稳定；对方值得借鉴的是**生命周期与安装体验**，不是计费与云端。

## 5. 建议（按优先级）

1. **发布我们自己的 skill（本批已做）**：`skills/openfigura/SKILL.md`，
   把 preflight→generate→inspect→print-check→render→export 与安全边界
   写成流程；引用 MCP 镜像表。
2. **补一个“等待/状态”说明而不是新动词**：我们已有 `workflow-status` 与
   阻塞式 `generate`；在 skill 与 usage 中明确长任务超时策略，避免 agent
   把长任务当失败重试（Meshy 的“创建不重发”语义值得写进我们的契约文档）。
3. **`--dry-run` 计划预览**（ROADMAP 已有提案）：把 workflow 提交前的步骤
   与预算（耗时/面数/后端可用性）打印出来；不涉及计费。
4. **切片器/打印交接先不做矩阵**：Meshy 做 7 种切片器探测；我们维持
   “文件 + 一条 Blender 验证路径”，如未来做，只做单一切片器的显式交接，
   不做插件矩阵（ROADMAP Rejected 已写）。
5. **不必补**：积分/余额/usage、云端任务队列、Creative Lab 商品线。

## 6. 证据

| 文件 | 内容 |
|---|---|
| `meshy-mcp-readme.txt` | MCP server README（28 工具、价格、重试语义、切片器） |
| `meshy-cli-readme.txt` | CLI README（登录、make、dry-run、JSON、api 逃生口） |
| `meshy-agent-install.txt` | meshy-3d-agent 的 INSTALL.md（skill 安装/设备码/安全边界） |
| `meshy-agent-skill.txt` | 404 记录：skill 内容不在仓库根，按 install 中的 skills/ 子目录分发 |
| Hi3D i18n | `../2026-10-16-meshy-hi3d-review/hi3d/messages-zh.json` 中 `mcp.*` |
