# 夜间接手复核与验收入口

时间：2026-10-09，Asia/Shanghai。接手版本 main `f354678`。
本轮在 `codex/3d-loop` 开发；无重写历史、无强推，用户未跟踪素材保留。

## 已复现并修复的交付问题

- NC 授权参数必须为真正 Boolean；字符串 `"false"` 不再被转换为接受。
- 执行器的 annotation 必须为声明并校验 hash 的输入。直接调用也把模型和
  annotation 复制到私有快照，原文件不交给外部预处理程序。
- 所有动作候选完成独立 gate 后才发布；后续 gate 抛错时不留正常交付候选。
- 蒙皮转移缺失／非零未赋权证据时拒绝交付，失败 GLB/Blend 隔离。
- OBJ/USD 随附 MTL/纹理，依赖文件逐一哈希；每资产独立子目录避免纹理同名覆盖。
  Blender 5.2 USD 纹理参数通过 RNA 探测，不使用不存在的参数。
- 缓存身份包含 engine、adapter、worker、可探测二进制；动画额外包含接触闸，
  导出额外包含格式转换器，修复代码后不复用旧安全判定。
  Pixal GGUF 目前只有尺寸和修改时间身份，不能据此声称权重内容完整性已校验。

独立复核发现组合缓存依赖遗漏，已新增红测再修复。测试命令：
`PYTHONPATH=src /Users/reynoldhu/Desktop/OpenFigura/.venv/bin/python -m pytest tests -q`
在开发 worktree 执行；首次全量 270 passed，后续新增修复以 PROGRESS 最后条目为准。

## 新增烘焙能力

`bake` / `figura_bake` / `engine.execute(..., 'bake', ...)` 共用核心实现。
CPU Cycles 高模到低模 tangent normal、AO、可选 albedo，输出 GLB、打包 Blend、
PNG 和报告。目标必须是已有 UV 的单个静态网格，骨架前执行；原始 UV、三角形
数、输入 hash 保持不变。粗 bounds overlap 不代表局部对应准确。
覆盖统计是 alpha 加 margin，**不是射线命中覆盖率**，非恒定图也不是画质验收。

真实命令脚本与产物根目录均为：
`/Users/reynoldhu/Desktop/OpenFigura/.local/runs/openfigura-review-2026-10-09/`。
桌面旧批次已迁入仓库本地目录并逐文件hash验证；历史报告/命令绝对路径保持
原记录，按`.local/catalog.json`映射访问，不改写证据hash。

| 证据 | 实际结果 |
|---|---|
| `verify_integration.py`, `bake-execute.json`, `bake-mcp.json` | executor 与真实 MCP 烘焙调用通过 |
| `bake-fixture/`, `bake-albedo-fixture/` | 高低球体：normal/AO 与彩色 albedo 非恒定，UV/面数/输入不变；无 UV、错位负测拒绝 |
| `format-proof.json`, `delivery-packaged-obj/`, `delivery-packaged-usd/` | OBJ MTL 引用存在；USD 纹理依赖存在且 hash 正确 |
| `run_scifi_bake.py`, `scifi-bake-job.json` | 958,816→95,881 面，1024 三贴图产出；AO/albedo 有效 alpha 仅 0.2867%，实看为黑底散点，**不可视为可用烘焙资产** |

### scifi UV 根因与修复对照

旧UV重展开将已有图集变成39,501个岛，面积仅0.00574%图集，95,881个三角形
全部低于1024贴图半像素。缩margin/临时焊接重新展开仍不足，未选作交付方案。
优化阶段继承UV面积41.732%，因此新`uv`默认`mode=auto`保留技术合格既有UV；
显式unwrap/repack才改变映射，并用margin_pixels/resolution控制间距。
非有限、退化、单位图集外和极稀疏UV在导出前拒绝。

`scifi-uv-trial/`下`low-protected.mesh-report.json`、`bake-1024/ledger.json`、
`bake-1024/bake-report.json`及`render-before/`、`render-after/`构成真实证据。
1024/16samples三贴图烘焙9.17秒；AO/albedo alpha含margin覆盖约92.44%，
**不是射线命中率**。同一相机8samples真实帧从黑色资产恢复护甲/金线/皮肤颜色。
root已查看真实前后帧；用户美术接受仍pending，指/发几何和动作问题未修复。
原高低模hash不变。面积检查仅启发式，不能证明UV无重叠；当前限单位图集，
UDIM/多独立atlas应显式选择preserve并检查，不将auto当作通用UV保留保证。

## 本机生成能力：纠正运行时缺失判断

实际 runtime 与 GGUF 在 `Desktop/Local/Opensource/pixal-local-trial-2026-10-05/`。
本轮未下载或安装新运行时；新增本地 profile 发现机制，显式环境配置优先，
profile 在 `$HOME/.config/openfigura/pixal3d.json`，机器路径不提交进 Git。

`run_generate.py` 实际 Pixal Metal 生成通过（seed42，1024，2048atlas）；
`generation-job.json` 给出阶段与 hash。`continue_generated.py` 完成检查、四视角
渲染和 MIA CPU 52 关节结构／fit 验证，见 `generated-followup.json`。
输入是 golden 当前半写实小满，**不是旧版 chibi**；旧 chibi 手腕问题仍未解决。

`run_generated_motion.py` 31 帧重定向在 Blender worker 超时 600 秒，见
`generated-motion.json`。没有通过的本轮新动画，不得展示旧动画冒充。

随后唯一低模链见`generated-low-motion.json`及`generated-low-motion-tasks/`：
947,962→75,835面（5.76s）→1024三图bake→MIA52关节（9.52s）全部实际通过，
31帧重定向在第4帧未过2mm接触间隙而被拒绝，保留失败账本；约58秒结束。
原高模hash不变，低模速度问题已改善，但**不碰撞模型仍未交付**。
此重烘焙继承白眼/错误口袋，不能宣称修复输入到精细脸部质量。
补充真实静态rig render显示严重全身黑裂纹/斑点，相比原生成明显劣化，root
已亲自看帧；技术产出不得作为视觉通过。待做分贴图消融定位。

## 视觉与接触负结果

- 新生成小满白眼、口袋灰凸条；纹理丢失在原始 BaseColor 已存在。
  `face-projection-trial/README.md` 的原图投射保留几何/UV且恢复瞳孔和口袋 RGB，
  但仍有嘴部双轮廓、侧脸接缝、错误口袋几何；诊断候选未替换基线。
- `scifi-contact-trial/REPORT.md`：上臂及整肩链替代搜索均未过 2mm 间隙闸，
  最好仍有 10／14 个表面交叉。部分手区域顶点身体权重高于手臂权重，且区域
  混入发／披风／装甲，应先审计分区与蒙皮；不能认定换 UniMate 就能解决。
- 现有 contact 只检查所声明区域和整数帧，排除过渡三角形，不证明全身、连续
  时间、闭体积包含或布料物理意义的不碰撞。

全部 `visual_approval` 留给用户；单测、结构通过和美术接受分别记录。
Windows/CUDA 连接方式仍缺。UniMate 权重尚未真实运行，Studio 全功能仍有大缺口。
