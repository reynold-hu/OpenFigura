# OpenFigura 3D 完整验收状态

日期：2026-10-09（Asia/Shanghai）。**进行中，未达最终验收**。
接手 main `f354678`；开发 checkout
`/Users/reynoldhu/.codex/worktrees/openfigura-3d-loop`，分支 `codex/3d-loop`。

## 用户目标

精细图生3D → 部件拆解 → 自动骨架/蒙皮 → 不碰撞动作 → Blender 真实播放，
以及固定版本 3DGenStudio 全功能独立复现。人审美术必须另行认可。

## 本轮事实

- 接手228 tests；首次新增全量270 passed，最新总数以 PROGRESS 为准。
- 修复NC字符串接受、annotation未声明/缓存无hash、外部预处理写原输入、
  后续gate失败残留交付物、transfer未赋权、OBJ/USD丢sidecars。
  增加组合缓存身份（生成器+gate，export+格式转换器），独立复审已进行。
- 新增CPU normal/AO/可选albedo高低模烘焙，CLI/MCP/execute镜像，真实
  球体与MCP/executor/OBJ/USD依赖证明在本地批次目录。scifi三贴图字节产出但仅
  首轮0.2867% AO/albedo alpha有效，实看黑底散点；UV岛39,501个，面积仅
  0.00574% atlas。已修auto保留有效继承UV；真实1024重烘焙alpha含margin
  约92.44%，前后真实帧恢复护甲/金线/肤色，美术接受仍pending。
- **纠正“本机没有Pixal运行时”**：已有Metal binary/GGUF，新增profile
  已发现并实跑新半写实小满生成。四视角、MIA CPU52关节结构/fit通过。
  旧版chibi未解决；新模型白眼／口袋几何和纹理不达精细目标。
- 新生成模型31帧重定向worker在600秒超时，未产出通过动画。
- scifi肩链替代搜索也未过闸，局部蒙皮权重和区域混入装甲/发/披风有问题；
  UniMate未保证能修正，CUDA路径仍待实际验证。已修preprocess失败继续运行、
  shell切换错误Python；真实smoke缺loguru/torch/defaultenv，未跑推理。
- 所有visual_approval pending。此前bunny真实播放证据保留，不冒充本轮新模型。
- Studio95工具矩阵仍有大量absent，烘焙/transfer/格式只是部分能力补齐。

完整审查、命令和验收入口：`docs/2026-10-09-handoff-review.md`。
产物根：`/Users/reynoldhu/Desktop/OpenFigura/.local/runs/openfigura-review-2026-10-09/`。
用户10月9日要求统一治理：桌面10个旧批次已迁入主仓库`.local/runs/`，
`.local/catalog.json`及manifests有旧→新映射/逐文件hash。历史证据不改写。
以后全部产物留主仓库`.local`（gitignore），worktree也复用此固定根。

## 夜间接续

已建立本线程30分钟heartbeat `openfigura-loop`，用户已授权持续开发。
先读STATE/TASKS/CONTRACT和Git状态；检查已有job JSON/进程，禁止重复重任务。
job入口：generation-job.json、generated-followup.json、generated-motion.json、scifi-bake-job.json。
生成pass／rigpass／motionfail；scifi第一轮烘焙是技术pass但视觉不可用。
scifi-uv-trial/bake-1024为有效继承UV的后续候选；旧first job勿误用。
`generated-low-motion.json`的唯一低模试验已结束：947,962→75,835面，1024三图
烘焙和MIA52关节通过，retarget被第4帧2mm间隙闸拒绝；原图/高模未改。
新增真实static render显示全身黑裂纹/斑点，root已看图确认劣化。分贴图消融已做，
新批次`.local/runs/2026-10-09-xiaoman-map-ablation/`：原高模H平滑，优化后A
未烘焙已裂，完全无贴图clay I仍裂。因此先审计optimize几何/custom normals/
shading，不把烘焙或UV当已证明根因。C/E等图证明Cycles原occlusion组不连Surface。
消融summary及geometry统计已完成：1e-6世界位置聚类后，边界边high0→optimized
84,873，baked相同；优化后重复面0，OPAQUE alpha1。明确几何缝/孔在optimize
出现，法线可能加重。连通性恢复/降面已用独立副本验证；原模型不焊接、不改写。
本轮已做exact weld诊断：裂纹明显消失，边界84,873→422；但Decimate引入
58重复面，仍2,502非流形边。安全optimize已接入默认精确合并、前后计数/存活面
UV签名核验、导入前有限数值检查和共享实例隔离。正式源小满被duplicate回归闸
拒绝，没有生产GLB；球体/开放平面等真实正例通过。见docs/mesh-optimization.md。
产物批次：2026-10-09-weld-optimize、optimize-tool-verify、optimize-review-verify。
不要重跑相同MIA或同动作参数，先查看failed contact诊断与region/skin定义。

优先：正规非流形/重复面repair（保留UV/明确删除/填面与部件风险）→安全降面复验
→分区/蒙皮审核与动作闸→全链文件与Blender帧
→ Studio矩阵逐项独立开发。重定向失败不能靠重复同算法搜索或降低阈值掩盖。
低模和贴图必须联合保留细节，不能拿低分辨率截图证明精细。

CUDA访问仍缺，可继续Mac CPU/Metal；不降低碰撞阈值、不重标区域掩盖失败。
有限区域/整数帧检测不能声称全身连续不碰撞。无重写历史/强推；不覆盖用户
golden/参考图/权重，验收前不替换基线；硬件和许可受限项如实保留。
