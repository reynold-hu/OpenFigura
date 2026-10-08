# OpenFigura 3D／2D 技术接入复核与开发决策

本轮复核日期：2026-10-08。证据来自已固定的本地源码与上游文档。
“源码已读”“接口已实现”“实际算法通过”“视觉获认可”是不同状态。
本轮没有安装新生成模型、运行新第三方安装器、复制 3DGenStudio 源码。

## 接入矩阵

| 项目／能力 | 源码或文档入口 | 决策与限制 |
|---|---|---|
| 3DGenStudio 工作流 | `batch/runner.js`、`mcp/comfyRun.js` | 学习后台持有长任务、先订阅后提交、防止快任务丢事件。批处理按阶段串行且活跃状态在内存；独立实现持久状态和原子领取。其 Community License 代码不合并。 |
| 3DGenStudio 蒙皮转移 | `skinTransfer.js`、`meshRigTransfer.js` | 最近表面重心插值、重合顶点统一权重值得独立实现；保留目标 GLB 图像、UV 和材质。空间重合不应无条件绑定：独立衣物／缝隙要按部件约束。 |
| Pixal3D | 现有 adapter 和原先 Mac 证据 | 继续作为已有生成路径；完整框架内长任务仍需单独验收，不用单次优秀结果推断全类别质量。 |
| PartCrafter | README、部件联合生成流程 | 用于需要部件结构的候选路线；上游声明至少 8GB CUDA，可减少部件／token。不是把人像裁成脸／手后硬拼。未在本机推理。 |
| Hi3DGen | README、法线条件几何流程 | 图像法线用于几何条件；额外法线误差可能变成几何错误，需要与原图及粗模比较。仅源码研究。 |
| DetailGen3D | README、粗模精修流程 | 作为独立候选精修器，不覆盖高模、UV、骨架；表面／轮廓误差与细节改善一起评估。仅源码研究。 |
| Hunyuan3D 2.1 | README、`hy3dpaint` | 官方声明几何 10GB、纹理 21GB、合计 29GB。不放进统一“8GB即可”默认档；形状／材质分离、按需加载、GPU节点可选。未实测。 |
| UltraTex／Marigold | Studio 工作流及 setup 节点配置 | 多视角补全与去光照／法线参考；必须核查原节点和权重许可，不能只从 Studio 名称推断已安装。 |
| Pixel Match | 现有 `photo_paint` 集成 | 源像素恢复图案；只处理可见表面，不能修手指、侧面几何或推断完整 PBR。 |
| MIA v1 | 现有 worker 与实际 CPU 日志 | 保留可用实验后端；对照 Bunny 成功、小满手腕预测失败。模型误差不能由调度框架掩盖。 |
| SkinTokens | 原仓库 README 42 行 | 上游要求 NVIDIA 至少 14GB；源码 MIT 与权重许可分别核查。重骨架模型可选，不作为基础安装依赖。 |
| MocapAnything | 原仓库、Studio 独立服务 | 当前研究的是非官方实现；输入视频与目标骨架、可见动作误差分别验收。未运行。 |
| Godot／Blender 动作 | 已有 retarget 与 IK worker | 同名骨架重定向、局部接触修正；整数帧手／身体检查不等于全身连续碰撞或布料物理。 |
| CoACD | Studio collision service | 用于物理代理，不能替代动作穿插检查。另核查原库许可后接入。 |

## 2D 项目实码复核

新增本地源码均位于 `~/Desktop/Local/Opensource/`，没有执行安装器或导出样例。

| 项目 | 固定版本／代码入口 | 接入决定 |
|---|---|---|
| GodotPixelRenderer | `078f2078fb9eb22b0f7d0dbd64d24a3638050c5b`；`PixelArt.gdshader`、PixelRenderer 脚本 | MIT；固定低分辨率渲染、palette、outline 与动画导出可作为可选 Godot 后端。当前 shader 先调色板后继续量化／描边，最终颜色可能不属于原调色板，仍要输出审计。无需神经模型 GPU。 |
| pixel-art-addon-mod | `f13502c1fa71fd92e3969f35e9edeab17f4da52d`；`__init__.py` | 源码头 GPL-3.0-or-later；声明 Blender 5.2，设置 render filter 等。不是直接安装就保证兼容，先独立 headless 小样测试。未复制代码。 |
| Pixelorama | `016b11e9c917055926a2d20438717c9ce41f846b`；`src/Autoload/Export.gd` | MIT；Sprite Sheet、帧时长、JSON、图层／tag 对人工精修和可编辑交付有价值；优先外部 CLI，避免把整套编辑器嵌进核心。 |
| Aseprite | 官方 CLI 与 README | CLI 支持 sheet/data、palette、indexed 转换；当前软件使用 EULA，不当作宽松开源组件打包。用户已有安装时可选连接。 |
| Pillow | 官方 Image API | CPU 图像处理低门槛；RGBA 默认量化不等于共享固定调色板，应分别处理 RGB 与 alpha，并声明算法与版本。只在像素 optional extra 中加载。 |

项目一级风格规范负责画布、像素比例、固定调色板、描边策略、阴影策略、FPS、锚点、透明背景。
它是可验证的参数契约，不能承诺凭这些字段自动产生满意画风。

## 双轨约束

3D 转 2D 优先适合连续角色动画；直接 2D 适合已有人物原稿、UI、道具与特效。
直接 2D 角色动画还可以使用 Godot 2D 骨骼／分层精灵；但变形会破坏低分辨率像素网格，
必须再对齐、做轮廓清理，仍需要人工确认。本轮没有声称运行了自动生成 2D 动画模型。

固定相机／灯光／画布／骨架动作能减少身份和比例漂移，但仍有以下问题：

- 每帧自动框选会让脚底锚点漂移：整段序列共享相机与原点，不逐帧归一化。
- 每帧自动选颜色会闪烁：整段序列共享调色板；确定性抖动也需跨帧坐标一致。
- 法线变化和亚像素边缘会闪烁：降低抗锯齿不是完整解决方案，需检查边缘与静止区域时序差异。
- 小手、眼睛在 32／64 像素可能消失：需要角色比例适配、轮廓分层和人工局部修订。
- 改材质、拓扑会破坏 skin／UV：生成新的候选，保留高模、低模和关联数据，不整包重写原资产。

## 本次开发次序与原计划修正

先实施资产哈希引用与不可变风格规范、持久阶段状态，再通过 CLI／MCP 共享这些能力。
不同进程可能同时提交，因此阶段状态采用标准库 SQLite 事务与 compare-and-set 领取，
不让多个进程直接覆写同一个 JSON。`provenance.json` 继续保留已有后端日志，
新的 `workflow.sqlite3` 保存工作流事件；查询／导出给出明确来源，不假装旧步骤已经受工作流管理。

阶段恢复只允许失败／取消步骤重新入队；进程中断留下的 running 需要明确恢复记录，
不能因为前端超时就重新执行。缓存要核查输入和输出实际哈希以及后端版本，
路径移到其他任务的缓存复用暂缓，先保证同任务引用可追溯。

随后接固定序列渲染和 CPU 像素化、资源队列、拓扑／烘焙、工作台；全部仍属于已批准产品范围。
旧实现计划将多个大系统和研究后端写成一轮完整交付，测试与代码仍为概要。
现在按可验证增量推进，并以实际代码、CLI/MCP调用和测试记录更新进度，
不把注册未实现 adapter、声明 8GB 档或增加 UI 当作端到端已经完成。

## 一手来源

- [3DGenStudio 固定版本](https://github.com/visualbruno/3DGenStudio/tree/3095871a2b8fc3182591f82d5de1a1b36f8bcbd0)
- [PartCrafter](https://github.com/wgsxm/PartCrafter)
- [Hunyuan3D 2.1](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1)
- [SkinTokens](https://github.com/VAST-AI-Research/SkinTokens)
- [GodotPixelRenderer](https://github.com/bukkbeek/GodotPixelRenderer)
- [Blender 像素插件源码](https://github.com/Tramshy/pixel-art-addon-mod)
- [Pixelorama CLI](https://pixelorama.org/user_manual/cli/)
- [Pixelorama MIT 许可](https://github.com/Orama-Interactive/Pixelorama/blob/master/LICENSE)
- [Aseprite CLI](https://www.aseprite.com/docs/cli/)、[当前许可声明](https://github.com/aseprite/aseprite/blob/main/README.md)
- [Pillow Image API](https://pillow.readthedocs.io/en/stable/reference/Image.html)
