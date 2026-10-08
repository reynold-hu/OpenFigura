# 3DGenStudio 技术栈审查与 OpenFigura 接入方向

已克隆到 `~/Desktop/Local/Opensource/3DGenStudio`，审查版本
`3095871a2b8fc3182591f82d5de1a1b36f8bcbd0`。本轮只读取源码；没有执行其安装器、
启动服务、下载模型或调用收费 API。下面区分代码里已有的能力与本机实测。

## 对 OpenFigura 最有价值的部分

| 能力 | 实际技术/代码入口 | 接入方式与边界 |
|---|---|---|
| 生成工作流 | ComfyUI API、`mcp/comfyRun.js`、`setup/comfyui.json`，TRELLIS.2、Pixal3D、Hunyuan 2.0/2.1 节点 | 独立 ComfyUI 后端；工作流版本、输入输出哈希、节点依赖一起记录。不是装了界面就有模型。 |
| 材质精修 | Qwen Image Edit、UltraTex 多视角、Marigold v2 法线/去光照、投射与烘焙工作流 | 与几何生成分开；参考图投射保图案，多视角生成补背面。高低模烘焙必须保留源模型。 |
| UV/拓扑 | `python-server/app/services`：SciPy LSCM/ARAP、PyMeshLab、体素壳、表面重投射、可选 QuadriFlow | 优先接独立库。体素壳可能合并手指/薄片；四边形必须记录实际占比、形状误差及可编辑原稿，GLB 仍是三角化交付。 |
| 高低模蒙皮转移 | `skinTransfer.js` / `meshRigTransfer.js`：最近表面、重心坐标、重合点权重一致、平滑、直接追加 glTF 数据 | 借鉴算法与数据契约，独立实现。不能用会剥离 skin 的通用网格读写器重写整个资产；UV/PBR/动画应独立验收。 |
| 自动骨架/蒙皮 | 独立 SkinTokens/TokenRig 服务，`thirdparty/skintokens/rig.py` | 从 VAST 原仓库接入，不复制 Studio 包装代码。官方要求 NVIDIA/CUDA、至少 14GB 显存；本 Mac 未运行。 |
| 视频转动作 | MoCapAnything V2，目标骨架条件、视频推理、BVH 输出 | Studio 使用的是 MIT 的非官方实现；需要单独评估模型、目标骨架和视频效果。已拉取原仓库，未安装/运行。 |
| 文本转动作 | NVIDIA Kimodo、独立文本编码器服务 | 专用动作模型，不是让聊天 Agent 写逐帧姿态。文本编码器占用很大；应与骨架服务分开加载。未实测。 |
| 后台长任务 | `batch/runner.js` 的阶段执行、取消、结果卡片续跑；MCP 共用执行器 | 值得采用后台任务所有权、结果引用、参数 schema。当前代码按阶段 `await` 串行；状态在内存，进程重启不是中间计算检查点恢复。 |
| GPU 分工 | Warp 最近点投射、CuPy 体素操作；拓扑重网格仍跑 CPU | 记录每一阶段的实际设备。CPU 多任务和单 GPU 大模型排队分开，不把“可并发请求”当成“显存足够并发推理”。 |
| 碰撞代理 | CoACD、多凸包、盒/球导出，`services/collision.py` | 用于引擎物理代理；不能替代人物动作中的手/衣服穿插检查和 IK 修正。 |

## 许可证决定接入策略

项目自身采用 [Community License](https://github.com/visualbruno/3DGenStudio/blob/3095871a2b8fc3182591f82d5de1a1b36f8bcbd0/LICENSE)，
包含软件售卖、付费托管/订阅及商业打包限制；摘要另有再分发限制。不能把它当成
没有附加限制的代码，直接并入 OpenFigura 的 AGPL 代码。这里没有复制项目源码。

采用“学习架构、独立接底层项目”的路线。已另外克隆：

- SkinTokens：`~/Desktop/Local/Opensource/SkinTokens`，MIT 代码，
  `273b691d35989d71cd17ff2895fdc735097b92d1`。
- MocapAnything：`~/Desktop/Local/Opensource/MocapAnything`，MIT 代码，
  `c99fb22c2f6001958c73c197065322b98ca0b93b`。

代码、模型权重、模板、示例角色和动画各自的许可分别记录；不因为工作台对输出的
描述就推断上游组件或输入资产没有限制。

## 更全面的产品应怎样组合

OpenFigura 核心继续是外部工具层，Agent 只选择参数、提交任务、读取结果。
算法运行、模型驻留、动作处理和质量拒绝由工具负责。可选工作台以后只展示资产版本、
流程与结果，不把任务执行放进网页标签。

按以下顺序独立接入，下面是后续计划，不是已交付功能：

1. 持久任务状态与 GPU 资源闸门：`submit/status/cancel/resume`，明确阶段输入输出、
   失败原因、设备/显存需求。默认每张 GPU 一个重模型任务；CPU 阶段单独设 worker 数。
2. ComfyUI 后端与版本化工作流包：先接已有 Pixal/TRELLIS/Hunyuan 的几何/材质分阶段，
   跨阶段保留原图、法线、原始网格、相机与烘焙数据。
3. 拓扑→UV→高低模烘焙→蒙皮转移：先小满/scifi 两个样本验收轮廓、五官、图案和接缝，
   保持 editable quad mesh 与 triangulated game mesh 两套交付。
4. SkinTokens 与视频/文本动作后端：在真实 GPU 上实测后注册，不用不可运行的空适配器
   充当已经支持。复用骨架连续性、变形、区域接触和真实引擎渲染检查。
5. 可选资产工作台：复用 CLI/MCP 核心，支持版本比较和人工验收；不另造 Agent 框架。

## 与这次实际工程的结合

已实现的外部算法链是 MIA v1 自动关节/蒙皮 → Godot 原生重定向 → Blender IK
接触修正与检查。它是独立实现，不取自 3DGenStudio。

MIA 在 Mac CPU 真正运行；作者对照角色通过，小满手腕定位失败，已被拦截。
这说明“工具稳定执行”和“专用模型对每个角色都准确”是两个验收项目。
SkinTokens 是值得用真实 GPU 比较的下一后端，而不是把 MIA 失败藏起来。

证据与代码记录见 `2026-10-08-neural-rig-trial.md`。本轮没有声称本机跑通了
3DGenStudio 的 SkinTokens、MoCapAnything、Kimodo 或多视角材质生成。
