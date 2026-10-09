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

本轮repair试验已结束，见docs/2026-10-09-repair-trials.md：Blender保守清理仍有
2493非流形边；MeshLab删面使边归0，却增加边界/碎片和UV冲突面删除。
内部索引编辑器已验证原属性字节保留，候选仅diagnostic；其后降面仍因22个
新重复面拒绝。不要重复这三条同族repair/Decimate试错。PyMeshLab独立ARM64
runtime可用，不代表正式人物repair后端可用。

属性约束gltfpack原配置与-sv各一次已验证，均增加非流形/重复面，未注册为
生产backend。不要重复这两配置或ratio网格搜索；详见docs/2026-10-09-gltfpack-plan.md。
独立Studio原点功能已完成：pivot CLI/MCP/execute统一，静态ground/center平移，
identity资产根+offset child保留原BIN/UV/法线/材质；真实三接口与Blender帧通过。
发布身份/hash与竞争失败隔离经复审，具体限制见docs/pivot.md。

接续可推进：原始高模的受控动作/分层动画能力（不用未通过低模；不改碰撞区域/
2mm阈值；任何受限动作必须如实描述）、原图细节恢复、或独立Studio资产库/批处理。
简化问题保留未完成，先做薄层/属性保真架构比较而非继续同输入删面/比例调参。

最新原始高模蒙皮诊断已完成，见docs/2026-10-09-high-skin-audit.md及
`.local/runs/2026-10-09-high-skin-audit/`：独立手腕30°探针使裤腿凸起，
Left/Right腿或髋主导顶点302/225个移动超过2mm。6例原预测top4权重追溯
吻合，指尖与腿混合已存在MIA预测；不是只凭关节数/未赋权0能判通过。
三帧实看，源hash未变，无动画交付。接续先研究手/裤腿区域约束与蒙皮质量
报告，不继续旧IK或把这两次诊断手腕旋转当成碰撞安全动作。

表面图试验也完成：2026-10-09-geodesic-skin-trial，确切原顶点顺序匹配，
手/腿高置信神经种子多源距离仅诊断，未修改权重。Left红标样本三视角局部
真实帧确认在裤面旁；部分点却更近手种子，直接geodesic分类不可靠。
不要同配置反复传播/删权重。下一步先可审查skin质量报告及原图/UV材质
辅助语义种子筛查；不能用主导组或神经置信度当真值。见geodesic-skin-trial文档。

UV颜色诊断和一次局部权重候选已完成，见docs/2026-10-09-uv-skin-trial.md。
原标签计数腿/髋>2mm形变302→38、225→30，但真实局部帧仍有裤面尖刺，
故候选不通过、未注册生产后端/未跑碰撞闸。选择1045实际改变1044，独立
验证geometry/UV/材质引用保持、无集合外变更、无未赋权；不等于全属性字节
证明。脚本性能中止和初验证no-op断言失败均留档。不要重跑同色阈值网格。
下一步优先实现可审查skin质量报告工具（数值/不相邻骨族混合/覆盖/固定
探针极值与真实近景），不是继续仅修计数。现原高模的可靠skin仍未通过。

优先：工具适配及独立能力验证
→分区/蒙皮审核与动作闸→全链文件与Blender帧
→ Studio矩阵逐项独立开发。重定向失败不能靠重复同算法搜索或降低阈值掩盖。
低模和贴图必须联合保留细节，不能拿低分辨率截图证明精细。

CUDA访问仍缺，可继续Mac CPU/Metal；不降低碰撞阈值、不重标区域掩盖失败。
有限区域/整数帧检测不能声称全身连续不碰撞。无重写历史/强推；不覆盖用户
golden/参考图/权重，验收前不替换基线；硬件和许可受限项如实保留。
