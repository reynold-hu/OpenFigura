# Windows 八例生成结果、网格与并行/GPU 审查

日期：2026-10-06。审查版本：本机 OpenFigura `86ec07a`（干净工作树）；Windows 验收包是另一组未同步修改产生的结果。没有执行包内脚本，没有更改生产代码或重新运行生成。附件文档的结论作为待验证说法，不作为操作授权。

## 证据与边界

原包：`OpenFigura-review-2026-10-05.zip`；临时展开目录 `/tmp/openfigura-review-20261006-svsho8hq/`。11 个 GLB 的长度和 SHA-256 全部匹配附带 MANIFEST。8 个原输入在本机 golden/cases 中找到，逐个哈希匹配 Windows provenance。

重新渲染脚本、16 张同场景真实帧、网格统计：`/Users/reynoldhu/Desktop/Local/Opensource/openfigura-quality-audit-2026-10-06/`。`render_audit.py` 逐个归一化生成网格，同一 Cycles/AgX/灯光；拍正常脸、灰模脸和实际 Base Color 的 emission 视图。没有改变源 GLB。原始渲染与重渲染不能称为逐像素同图实验，因为输入人物和相机尺度不同。

当前本机源码测试：`.venv/bin/python -m pytest tests -q`，17/17通过。包内“22/22”属于未提供的 Windows 修改，未据此声称当前代码有那些功能。

## 1. 为什么不能先归因于 Windows/GPU 或写实风格

下午模型输入为 1024×1024 透明图，从用户 Q 版四视图中提取正面；SHA `b0c0486f…a8091a5`。Windows xiaoman-front 输入是1664×2496、无alpha的新图，SHA `0e970c8c…d39044`。原稿的人体比例、脸形、眼形、服装、发饰与构图都不同，前者明显大头，后者接近较长身材比例。名字相同不等于输入相同。

账本申报的生成参数基本相同：SV Q8 v1、seed42、res1024、max_tokens8192、atlas2048、webp off、require-gpu。Windows增加了自动抠图步骤；Mac采用已检查的透明前景。两条链的实际抠图结果、最终 svviews 取景以及各权重/runtime实文件哈希尚未在包中完整提供。

因此已确定的是输入与预处理不同；头部在整个主体中占比更小，是细节损失的有依据假设。GPU数值路径是否另有差异仍未知，需要同一最终输入、相同相机/参数与两端运行时/权重身份的对照。Windows日誌确认使用RTX4060 CUDA，并非没有GPU运行。

观察8组原稿/模型：写实半身 head-sculpt 的眼睑、耳廓、鼻唇比全身 xiaoman/silver-scarf 保留更多，但皮肤与细表面仍软化。盔甲大结构相对清楚；道具上的细金线/图案与人物眼妆都会丢失。复杂姿态、遮挡、薄发束属于额外难度。不能由这8个样本推出“写实都不好”或“Q版都好”。

## 2. 眼睛同时有几何和颜色问题

同灯光重渲染 Windows xiaoman-full，眼睛依然异常。灰模显示眼部存在深凹/形状缺失，纯颜色视图显示灰白瞳孔区域与粗黑轮廓；这不是只换灯光能恢复的。应按区域区分几何、Base Color、Metallic/Roughness，再选择修复方法。

包中有价值的实验：1536、不同seed、半身输入与更大图集。它们显示结果有差异，但本文不接受“43已经修好”“半身保证眼白瞳孔正确”等审美结论：已查看43和半身face.png，仍有明显形状/颜色偏差。1536改善部分轮廓却损失发饰，也不能自动选为更好档。

“单眼约1–2个DINO patch，所以没有任何高频信息、必然退化”是过强解释。patch不是丢掉内部全部像素的平均色块；还涉及编码、投影、生成随机性、几何解码与烘焙。小特征条件不足是合理机制假设，尚未完成逐阶段因果定位。需要保存各阶段实际编码图像、头部像素尺寸和中间结果。

### 建议验证顺序

1. 在Windows直接使用下午已检查的透明 `input-front.png`，跳过重复自动抠图，seed42/1024/8192/2048重跑。保留最终svviews与全日志，使用同一渲染设置对比。这个最小实验先回答“输入差异还是平台差异”。
2. 在Windows原图保持seed和参数，仅对照“原图→自动matte”与人工检查通过的alpha；比较眼/耳/白衣高光，不能只检查has_alpha。
3. 对同一角色分别测全身与脸部裁切。裁切生成出的头不能直接替换进全身：先检查identity、比例、颈部接口、材质再融合。采用局部头部细化或独立眼球/眼睑模板作为产品路线；不将其包装成已跑通功能。
4. 给同图2–4个固定seed候选，保存失败与配件缺失，人挑选。不要用更大atlas或更多tokens替代缺失的眼部结构。真实参数是否生效以运行日志与实际输出为准。
5. 眼睛颜色可试从原图投射/重贴图；深凹眼窝和缺失眼球需要几何修复。前视贴图对齐不能证明侧视或动画正确。

## 3. Mesh审查：面数很多，但不是动画拓扑

解析11个包内GLB及下午模型：全部primitive mode=TRIANGLES，没有骨架/动画；约92.3–99.9万三角面。GLB没有四边形原面表达，不能只凭GLB判断作者是否另有四边形源模型。当前包没有该源模型。

UV接缝会复制顶点，所以几何边检查前先按**完全相同位置**焊接。本轮不是直接对GLB原始索引数边；边界与非流形数均是这一口径的统计，尚未逐部位定位。

| 模型 | 三角面 | 坍缩UV三角面 | 坍缩UV比例 | 焊接后非流形边 |
|---|---:|---:|---:|---:|
| 下午已认可 | 972414 | 1610 | 0.1656% | 6527 |
| Windows xiaoman1024 | 955004 | 3190 | 0.3340% | 2053 |
| Windows xiaoman1536 | 923340 | 9618 | 1.0417% | 2503 |
| 写实半身1024 | 988674 | 2395 | 0.2422% | 2430 |
| 蹲姿1024 | 987182 | 935 | 0.0947% | 17682 |

1536不保证UV更好；非流形更多也不能直接判定更丑（下午模型并非最低）。坍缩UV是异常统计，不证明眼睛正好由这些面导致。当前inspect只查引用与属性，有它的作用，但ok不等于mesh可动画。

建议给后处理分三个产物：

- 原始高模＋原贴图：永久保留，供细节转移与回退。
- 实时静态三角低模：可配目标面数、最大表面偏差与法线/颜色重烘焙。
- 可编辑四边形源模型：保存Blend/OBJ等、实际polygon计数和quad比例；动画导出GLB仍可三角化。

QuadriFlow可以作为四边形候选；不保证面部/肩肘/手指的变形环线。进一步需要流形清理、保护区域、边流检查、UV和贴图转移、固定姿态变形验收。[Blender官方重拓扑说明](https://docs.blender.org/manual/id/5.2/modeling/meshes/retopology.html)

接口应区分 `generation.resolution`、`generation.max_tokens`、`mesh.triangle_target`、`retopo.quad_face_target`、`texture.atlas_size`，不能把它们混成一个quality开关。面数/四边形不直接恢复眼睛或改善材质。

## 4. 本机代码确认的GPU与并发缺口

### GPU

`backends/pixal3d.py:58` 的构命令函数只转发 seed/res/max_tokens/atlas/require_gpu；输入gpu=1、tex_res=1024或拼错参数时，静默忽略。已用mock runtime/models的纯构命令诊断复现，不执行外部模型。CLI/MCP只暴露seed/res，参数接口也未覆盖这些选项。

`backends/blender.py:49` 设置Cycles但没有设置Cycles device=GPU或启用具体设备；不能根据生成器CUDA日志声称渲染也用了CUDA/OptiX。生成与渲染是不同子进程，必须分别选择/探测/记录设备。[Blender GPU说明](https://docs.blender.org/manual/id/3.0/render/cycles/gpu_rendering.html)、[Cycles命令行设备选项](https://docs.staging.blender.org/manual/en/latest/advanced/command_line/arguments.html)

### 并行

当前本机 `scripts/run_golden.py` 是串行，无jobs参数。包文档声称Windows新增jobs，代码没有随包提供，因此还不能核查Windows是否已经实现正确资源控制。

`core/task.py:40` 允许相同name重复创建同目录并清空账本。已在TemporaryDirectory重现：第一次record之后第二次create，原entries变空。并行任务必须使用唯一run_id，name只作展示名；同目录拒绝重复创建/同任务加锁，账本须原子写与串行事件更新。

`base.py` 只保留日志末尾并且ledger丢弃stdout；有效tokens/纹理降档/减面/UV烘焙统计不完整。补全stdout/stderr文件、argv数组、runtime/weight hash、预处理与svviews hash、有效参数和设备证据。timeout/error/cancel也写失败记录，不能留下看起来新成功的旧文件。

`syscheck` 只探测设备总VRAM，没有当前可用VRAM、UUID、runtime执行兼容性与并发资格；仅binary/models路径存在不能证明后端ready。

## 5. 建议并发契约（尚未实现的设计）

```toml
[scheduler]
jobs = 4                       # 在队任务数；不是同时占用GPU的生成数
cpu_preflight_workers = 2
cpu_postprocess_workers = 1
max_active_jobs_per_device = 1 # RTX4060 8GB的保守起点，后续以峰值实测调整

[generation]
backend = "pixal3d"
device = "cuda"
gpu_index = 0
require_gpu = true
seeds = [42, 43]
resolution = 1024
max_tokens = 8192

[render]
device = "OPTIX"
gpu_index = 0
samples = 32
fallback = "error"              # 要求GPU时不能静默改为CPU

[mesh]
deliverable = "quad_source_and_tri_runtime"
triangle_target = 50000        # 示例预算，需按实际游戏/用途决定
quad_face_target = 25000
preserve_highpoly = true
bake_textures = true
```

这不是现有可用配置文件，只是目标字段契约，schema需要验证未知字段/类型/范围、像素分辨率支持和后端能力。CLI与MCP传同一schema到core，由各后端落实；Pixal的gpu_index转成真实 `--gpu`，Cycles单独枚举OptiX/CUDA/Metal并启用设备。CUDA_VISIBLE_DEVICES映射与物理GPU UUID都应记录。

调度器为确定性工具队列，放core：提交任务→排队→预处理→等待设备→生成→网格后处理→渲染→检查→完成/失败/取消。多GPU按设备分配；单GPU8GB初始只允许一个GPU占用步骤。BiRefNet、Pixal与OptiX若用同一GPU，应共享跨进程设备预约，不能各自线程池独占“1槽”却实际叠加。

不同任务CPU预检/复制/轻量检查可以与GPU生成并行；CPU减面与渲染有独立RAM预算。新增MCP submit/status/cancel或等价任务接口，长生成不必阻塞整个工具服务。不能只在run_golden加ThreadPoolExecutor就宣布全系统并行安全。

最低验收：两任务目录/账本隔离；同GPU互斥而不同GPU可并行；请求gpu=1实际传递；缺OptiX/设备失败清楚报错；timeout取消清理本任务子进程并释放设备；输出原子落盘；mock测试不替代Windows真机两任务运行、显存峰值/时间证据。

## 优先级与仍缺证据

P0：同一下午透明输入Windows重放；提供实际input-matted_cutout、svviews/transforms、完整stdout/stderr与模型/二进制身份。质量原因优先沿输入→抠图→取景→几何→贴图定位。

P1：局部脸/眼制作链；同步Windows当前未提交修改后再实现强类型参数、设备选择、唯一任务ID/锁与设备队列。当前本机旧版本不是Windows最新代码，盲改会丢失预处理/1536/jobs工作。

P2：高模/三角低模/四边形源模型三类交付，以及烘焙和变形验收。结构、外观、变形、吞吐、设备真实性分开验收。

尚未做：Windows/Metal同输入推理对照、Windows源代码修改审查、GPU并行真机验证、局部几何修复、重拓扑。本文提供诊断和可检验方案，不宣称质量已经修复或新增功能已实现。
