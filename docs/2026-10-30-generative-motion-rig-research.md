# Generative Motion Rig 与 Blender 开源替代调研

日期：2026-10-30。目标是判断截图所示 Disney Research SIGGRAPH 2026
“A Generative Motion Rig for Artist-Driven Motion Authoring”能否直接用于
OpenFigura，以及有哪些开源组件可以迁移。

## Disney 论文的真实边界

官方页面确认它是 Disney Research Studios 自研 Blender 插件，核心是
“generative keyframing”：艺术家操作稀疏姿态、控制柄、窗口长度和噪声采样，
生成完整动作；同时支持对已有 mocap 做编辑和延展。

官方公开页只提供论文 PDF和演示视频，没有插件源码、安装包、模型权重或
公开 GitHub 仓库。页面版权声明还写明资料用于非商业传播，未经作者许可不得
重新发布。因此不能把截图或论文里的交互直接复制进 OpenFigura，也不能宣称
已有公开可用的 Disney 插件。

## 可复用开源候选

| 项目 | 复用价值 | 机器与许可证边界 | OpenFigura 结论 |
|---|---|---|---|
| [UniMate-B3D](https://github.com/nopeburger/UniMate-B3D) | Blender 面板、单提示词、提示词时间线、姿态参考、Action 生成与应用 | Blender 4.2+；README 主要面向 Windows/CUDA；集成 GPL-3.0-or-later，上游 UniMate MIT；checkpoint 为 CC BY-NC 4.0 | **最高优先**。已有 OpenFigura UniMate 适配器可对照其时间线与 Blender UX，但商用产品不能默认使用 checkpoint |
| [Kimodo Motion](https://github.com/atticus-lv/kimodo_motion) | 本地文本动作、77-joint SOMA、Blender 内重定向；明确支持 Apple Silicon MPS | 插件 GPL-3.0-or-later；Kimodo-SOMA 权重 NVIDIA Open Model License；Llama 文本编码器 gated Meta license；Mac 需要约 32GB unified memory | **Mac/GPU 对照**。适合作为 OpenFigura 外部后端，不直接嵌入 GPL 插件代码 |
| [Rigger](https://github.com/asu37/Rigger) | Blender 4.2+/5.2；自动骨架、控制 rig、蒙皮、Mixamo/BVH 重定向、视频动作捕捉、脚底固定、Unity/Godot 导出 | GPL-3.0-or-later；模型/依赖另行核查 | **最适合补齐编辑与重定向工具层**，尤其是我们目前的手脚串权重、接触和导出缺口 |
| [HY-Motion Blender addon](https://github.com/haseebahmed295/motion_gen) | Blender 内文本到动作、隔离后端运行时、自动套用模板骨架 | README 要求 1.8GB checkpoint + 5.8GB Qwen GGUF；权重许可需单独审核 | **可作第二后端**；硬件门槛较高，不作为低配默认 |
| [Open Mocap](https://github.com/Larenju-Rai/open-mocap-blender) | 离线全身、手部追踪和重定向 | MIT；目前 README 明确只兼容 Blender 4.0 及更早版本 | **只取算法思路**，不直接接当前 Blender 5.2 |
| [text2motion/blender-integration](https://github.com/text2motion/blender-integration) | Blender 接文字动作平台 | 目前主要限制 Mixamo rig；服务/平台边界需核查 | 仅作为接口参考 |

另有 [Cartwheel MCP](https://github.com/Cartwheel/cartwheel-mcp) 和
[Uthana Blender plugin](https://github.com/Uthana/uthana-blender-plugin)，
但它们更偏外部服务或闭源基础模型，不能作为 OpenFigura 的本地默认路线。

## 与 OpenFigura 的组合方式

这篇 Disney 工作的真正可迁移部分是“稀疏控制 + 局部窗口 + 生成后再编辑”的
交互模型，而不是其模型代码。建议把它拆成四个稳定工具契约：

1. `pose_authoring`：读取 Blender/GLB rig，记录稀疏骨骼姿态和控制柄。
2. `motion_generate`：把姿态、动作文本、时间窗口、seed 和模型后端作为声明
   输入，输出独立 Action，不直接覆盖原模型。
3. `motion_edit`：对已有动作做局部窗口延展或替换，保留前后帧 hash 和来源。
4. `motion_gate`：逐帧做接触、根运动、脚底和异常拉伸检查；失败动作隔离。

OpenFigura 现有 `animate`、UniMate 适配器、Blender motion gate 和 skin-probe
正好覆盖第 2、4 步的一部分。下一步应优先吸收 UniMate-B3D 的 timeline/pose
reference 数据结构和 Rigger 的可控 rig/retarget 经验，而不是重写一套生成模型。

## 对当前角色问题的意义

这些项目不能直接解决小满当前裤面被手腕拉坏的问题。Rigger 的区域蒙皮、锁定
权重、脚底固定和 IK 工具可能帮助修复流程，但必须在 OpenFigura 的固定姿态
近景、三角拉伸和碰撞闸下重新验证。生成动作也不能掩盖错误蒙皮。

## 本地源码状态

以下源码已拉到 `~/Desktop/Local/Opensource/`，只做研究，尚未复制进 OpenFigura：

| 目录 | 固定提交 |
|---|---|
| `kimodo_motion` | `5517e873061f619e0beeaaade78de19cefa289bc` |
| `UniMate-B3D` | `afdaee78e047c2db1e7f95e4fcbb3c5e38f52f90` |
| `Rigger` | `c8f1d1b9a8729582c61fa0ffa9a658ec4f4f6e77` |
| `open-mocap-blender` | `1ec7457dad228661cbd8a1d98163e8288d3f7db5` |
| `motion_gen` | `70bac37a906d863d83d6946c1c616cfc37507dea` |

源码克隆不代表权重已安装，也不代表推理可用。所有模型权重、外部服务和
许可证都要在执行器账本里单独声明；OpenFigura 不把它们直接打包进 AGPL 代码。
