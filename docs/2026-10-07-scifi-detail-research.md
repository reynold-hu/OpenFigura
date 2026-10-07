# scifi-stride：局部细节路线调研与单例实验

日期：2026-10-07。所有结果保存在桌面；未安装新3D模型或改动当前OpenFigura后端。

## 目标与验收

只使用scifi-stride，比较原模型、原图回投模型，以及头部ROI独立生成。保留原GLB。对比使用同一相机/灯光/AgX/64 samples；完整转台检查正面、45度、侧面、背面，另外检查头部和躯干近景。效果需要用户认可；不以退出码或面数代替审美。

## 为什么高分辨率原图仍丢细节

### 本机源码可以确认的行为

本机runtime的release tag为v0.10.1-desktop-alpha，对应Git树1f432fd3f0689c504fa1e9b15b038c33584174d1。`src/image_preprocess.cpp`先把整图长边缩到1024，再按alpha>204计算前景bbox，加入1.1倍方形留白。`src/pixal3d_input.cpp`生成512和1024两组输入。不是所有原始像素都作为高分辨率条件保留。

- 1024是整幅画面分辨率，而非头盔、手指各自的分辨率。
- 当前SV调用先生成res32稀疏结构，再做512→1024几何级联；HR潜变量grid是1024/16=64。某个细部在图像条件与3D潜变量中都可能只有很小覆盖。
- 最终约百万三角面，是解码与后处理产物，不能证明每根线条或面部结构都有可靠条件。
- `--atlas 4096`是UV颜色图集尺寸，`--res 1536`是几何分辨率；两者都不会自动让输入特征超过1024。仅放大已经低清的输入不增加真实信息。
- `--max-tokens 8192`在当前1024 Pixal路径不是硬上限。源码的停止条件包含`hr_res==1024`，即使超过预算仍停止回退。在1536才可能逐级退到1024。因此不能根据参数宣称实际用了1536。
- `--tex-res`在此release的Pixal SV/MV路径中没有用于选择纹理解码分辨率；它影响的是另一个TRELLIS分支。不能把这个开关当成Pixal SV的有效精修开关。

这些机制解释了可能的瓶颈；尚未单独验证编码、量化、采样和几何解码各自的贡献。不能说小部位“必然无法生成”，也不能把Q8或Mac认定为唯一原因。

[本机版本预处理源码](https://github.com/raven38/pixal3d.cpp/blob/v0.10.1-desktop-alpha/src/image_preprocess.cpp)、[本机版本条件输入源码](https://github.com/raven38/pixal3d.cpp/blob/v0.10.1-desktop-alpha/src/pixal3d_input.cpp)、[本机版本级联与导出源码](https://github.com/raven38/pixal3d.cpp/blob/v0.10.1-desktop-alpha/src/trellis_cli.cpp)。源码快照保存在research/。

## 开源项目真实做法

| 方法 | 真实作用 | 本次取舍 |
|---|---|---|
| [Pixal3D](https://github.com/TencentARC/Pixal3D) | 把图像多尺度特征投影到3D位置，分别生成结构、形状和纹理；MV使用独立权重及相机矩阵 | 已有Mac移植；沿用作ROI诊断。局部裁图不能简单当成另一个全身视角 |
| [PartCrafter](https://github.com/wgsxm/PartCrafter) | 多部件latent +部件内/部件间注意力，联合生成可分离mesh；不是把2D裁片分别跑完后任意拼接 | 部件结构方向有参考价值；官方CUDA栈，不作为当前Mac即装即用方案。可拆分不等于五官或材质必然优质 |
| [HoloPart](https://github.com/VAST-AI-Research/HoloPart) | 已有mesh先分割，再补全被遮挡的部件 | 解决部件完整性；不能直接宣称补回原图的精确装饰 |
| [Hi3DGen](https://github.com/bytedance/Hi3DGen) | 图像→法线→几何，使用几何导向条件保留细节 | 可作为几何后端候选；官方安装依赖CUDA/spconv/xformers，不在此Mac直接运行 |
| [DetailGen3D](https://github.com/VAST-AI-Research/DetailGen3D) | 输入粗mesh+参考图，经latent flow生成细化几何 | 比无约束重生成更契合后续局部精修；官方脚本存在.cuda()调用，本机未部署，未宣称可直接MPS运行 |
| [Hunyuan3D-Paint 2.1](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/tree/main/hy3dpaint) | 在已有mesh上选视角，渲染normal/position条件，生成albedo及metallic/roughness，多视角烘焙并补洞 | 是“模型之后再做材质”的路线；官方6视角512推荐21GB显存，不能直接认定当前M5/16GB或4060/8GB能原配置运行 |
| [image-to-3dlab Pixel Match](https://github.com/Bingeljell/image-to-3dlab/blob/main/image_to_3dlab/photo_paint.py) | UV texel→3D位置→相机投影，计算遮挡、法线夹角和边缘权重，将原图RGB混入BaseColor | 无新增神经模型，numpy/Pillow即可；本次真实运行。它不修复几何，也不恢复物理albedo |

许可：本次执行的photo_paint取自Apache-2.0项目，保留LICENSE与NOTICE，commit钉在research/pixel-match-upstream.json。Pixal权重及DINO组件保留各自许可。其余路线只调研，后续集成需逐项检查代码和权重许可。

## 改进架构建议

推荐“全局形状 + 有约束的局部细节 + 独立材质”三层，而非整张图反复放大。

1. 保留高分辨率原图与alpha，另存512/1024实际条件图。标记头盔/手/装甲/细线ROI，每个ROI记录原图坐标、语义mask、遮挡和尺度。
2. 全身生成提供姿态、尺度和整体表面；局部几何必须以已有mesh/法线/位置或全局latent为条件。独立ROI生成只能先做诊断，拼回需要姿态尺度配准、连接边界、遮挡与多视角校验。
3. 纹理：准确相机标定下回投可见原图，斜面与遮挡降权；未见面保留原贴图或由多视图材质模型补齐。将表面颜色、粗糙度、金属度和法线分开处理。
4. 本例悬空金线用独立曲线/管状mesh更合适，发丝采用独立发束或hair cards，装甲铭纹优先纹理/normal。不能把悬空线画在披风上后称为几何恢复。
5. 交付与动画阶段才做重拓扑：保留高模源，烘焙到低模；可编辑quad源与运行时tri mesh并存。并行/GPU调度服务吞吐，不替代质量路线。

多视图原图必须一致并具备正确相机；从一张图生成出的背面是推断，不能作为真实性证据。裁图会改变内参/主点；当前Pixal接口只有FOV/c2w等有限参数，任意ROI不能直接作为规范全身MV输入。

## 本次实际实验

A：原始完整scifi-stride GLB（958816三角面，2048 BaseColor）。

B：仅原图回投，使用同一模型/UV/相机。为避免一张图改变背面整体色调，关闭上游默认的全局颜色匹配。所有非BaseColor的bufferView逐字节不变，未回投texel颜色不变。实际耗时与权重比例见pixel-match/provenance.json。

观察：头盔中央图案及装甲表面更接近原图；接缝、手部错位仍在。部分源图悬空金线被投到后方披风，说明“可见性”还不足以判断源像素属于哪个部件，需要部件mask及匹配检查。不能把B称为生产可用或几何改善。

C：从同一抠图裁出头盔、手及邻近头发，占满1024条件画面，seed/res/atlas/权重均保持原配置。未使用AI补画或新增真实信息。原图裁剪坐标保存在input/roi.json。此实验验证局部覆盖的作用；局部GLB不默认拼回全身。结果待实际生成完成后另记，未完成不得宣称成功。

## 追加结果与实验调整

### B1：按局部ROI限制纹理回投

初始全身回投在头发/手附近出现接缝，并把缺失的金线画到披风，因此收窄到人工圈定的头盔与躯干装甲。保持同一UV图集、几何、其他材质贴图；关闭全局颜色匹配。

- `roi-texture/model.glb`：958816三角面。
- 回投4.70秒，整张图集约2.49%的texel权重>0.5；这个比例是图集比例，不是可见表面质量分数。
- 所有非BaseColor bufferView逐字节相同，未回投texel相同，详见`verification.json`。
- 相同相机灯光的6张真实Blender渲染在`render/roi-texture/`。
- 观察：头盔金色中心图案更清楚，装甲纹理有所恢复；现有粗糙几何没有改变。此版本仅局部改善，未获用户审美验收。

### C：裁图生成被停止，不能据此下画质结论

运行1116.99秒，SS阶段生成3847个活跃体素，HR级联产生16250 tokens@1024，尽管请求预算为8192。HR采样未完成，无最终ROI mesh。

此时原始PLY与最终GLB对比已明确观察到后处理细部损失，故停止无约束裁图实验，把资源用于保留细部的受控测试。完整stdout/stderr和取消原因保存在`roi-generation/`。不能宣称裁图路线改善了几何，也不能说裁图生成失败或Mac无法运行；本轮只是主动取消，成本与全局一致性仍是需要解决的问题。

### D：从原始几何保留细线，未达到成品质量

原运行保留的PLY含2144914顶点、4337116三角面，已经做过部分焊接/补洞，但尚不是最终重网格/简化后的GLB。其灰模正面可见部分斜向细线；最终958816面GLB中大部分消失。`comparison-geometry-loss.jpg`是同相机、同灯光的真实灰模对比。

注意：PLY为Z-up，GLB导出器另外执行(x,z,-y)轴变换；渲染和追加几何按该约定处理，源码证据在research/mesh_glb.cpp。

实验按原图金色区域、人工检查的二维包围区域、与已有表面的保守空间网格分离提取原始细面，追加为独立mesh。保留52266面，合计1011082面，耗时2.22秒。主体几何未动，旧GLB二进制buffer前缀完全保留。来源和全部参数见`detail-retained/provenance.json`。

- 正面找回部分线条。
- 45度/侧面显示断裂、悬空碎片和错误深度，证明原始生成本身也有缺陷。不能把删除所有碎片视为错误，也不能把全部保留视为修复。
- 金色材质是选定的金属度/粗糙度＋原图颜色回投，不是已完成物理材质估计。
- 保留版是诊断候选，不能作为生产可用输出。完整转台在`render/detail-retained/`。

**最终判断：本次做出了局部纹理改善和真实几何细部保留的前后对比，但没有生成达到用户要求的完整成品。证据支持分部件、分阶段路线；不支持仅靠放大整图或增加面数即可达到Tripo水平。**

## 下一步应落实的最小改变

1. 保存重网格/简化前几何与实际条件图，逐阶段检查受保护ROI的轮廓、连接性和纹理，发现损失就标记，不只检查GLB能否打开。
2. 针对已定位细线，分离出连续路径并以曲线/管状mesh重建；保留源图、可编辑路径、厚度/深度参数及三视角验证。深度不确定时明确为假设，不能按单张图宣称还原真实背面。
3. 头盔/装甲表面采用ROI回投；先校准几何与部件对应，避免错误图案投到相邻部件。高分辨率UV或单独局部图集可以增加贴图容量，但不能补出缺失几何。
4. 要继续裁图生成，应切换到有粗mesh/normal/position约束的局部细化，而不是直接替换全身的头。优先在具备合适CUDA环境的机器验证DetailGen3D/Hi3DGen，并单独验证显存与许可。此处未安装或运行它们。
5. 一张图不足以确认背面与薄结构的深度。对需要成品质量的部件，应获取一致侧面参考或允许人工参数校准。

## 交付入口

- `comparison-main.jpg`：优化前、局部纹理、保留细线三列，含正面和45度。
- `comparison-head-cn.jpg`：头盔纹理特写前后。
- `comparison-geometry-loss.jpg`：原始/最终几何灰模对比。
- `roi-texture/model.glb`：局部纹理候选；`scifi-stride-roi-texture.blend`：可编辑查看。
- `detail-retained/model.glb`及`scifi-stride-detail-retained.blend`：保留细部的诊断候选，明确不达标。
- `input/raw-model.ply`、`input/calibrated-view/`：原始几何和输入相机；不依赖临时目录恢复。
- `verification.json`、每版provenance、inspect与完整日志：复验记录。
