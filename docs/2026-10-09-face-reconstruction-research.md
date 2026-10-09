# 脸部保真开源方案调研

日期：2026-10-09（Asia/Shanghai）。状态：官方资料/许可/部分源码核对完成；
未安装或实跑新增人脸模型，不声称本轮修复已通过。既有用户模型/参考图未改。

## 当前问题与路线选择

本地handoff记录已确认：新小满原始BaseColor中白眼已存在；之前photo-paint
恢复瞳孔RGB的候选仍有双嘴轮廓和侧脸接缝，不能把再次原样投射当作新修复。
鼻形/眼窝/嘴线需要几何或对齐，瞳孔/眉毛/唇色需要材质保真，两者分别验证。
不能从单张图恢复真实不可见后脑/耳背；增加输入像素不等于恢复未观测几何。

建议优先：CPU脸部对齐+可见性/语义mask的原图纹理路线；并研究FLAME 2023
Open可编辑脸部模板的关键点/轮廓拟合。GPU细化作为可选升级。
这是实施选择，不是各工具在当前角色上的效果证明。

## 候选核对

### FLAME 2023 Open：优先研究的网格基础

[官方页面](https://flame.is.tue.mpg.de/)与
[模型许可](https://flame.is.tue.mpg.de/modellicense.html)已明确单独发布
FLAME2023 Open，标示CC-BY-4.0，允许商业使用并要求署名、许可链接和修改
说明；页面还列有使用条款。不能把旧FLAME2023或旧Blender addon当成Open。

它是参数化脸/头模型，具有形状、表情及关节结构，不是任意图片直接出完整
角色的现成工具。可用于可控五官与后续表情；毛发、服饰、头颈接合另做。
低维参数拟合可设计为CPU路线，但本机速度和适合半写实玩偶的范围尚未测。

[FLAME_PyTorch](https://github.com/soubhiksanyal/FLAME_PyTorch)根LICENSE
写MIT，但`flame_pytorch/flame.py`文件头仍有MPG专有授权声明，且依赖smplx。
不能只看仓库徽标就直接迁移实现；模型Open许可也不自动解除旧实现/预测器
的限制。默认集成优先独立实现拟合与解码，或采用授权范围明确的实现。
原图纹理不要默认继承BFM/FLAME texture许可。

### MediaPipe Face Landmarker / 3DDFA_V2：对齐与测量，非精细建模

[MediaPipe官方](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker)
输出478个3D相对关键点、52个blendshape评分及变换。适合作为对齐约束，
不是带高质量皮肤/眼球/拓扑的游戏模型。代码/模型各自许可需要集成时固定
版本核对；不能把文档页代码示例Apache许可当成所有weights统一许可。

[3DDFA_V2官方](https://github.com/cleardusk/3DDFA_V2)有ONNX CPU、macOS
测试及OBJ/PLY/UV功能，代码MIT；默认120×120输入，作者注明闭眼定位不佳。
适合姿态/轮廓基线，不能拿快速alignment当精细眼睛恢复。统计模型/训练资产
来源需要独立核查，不把MIT代码当全部依赖自由商用。本机未安装实测。

### HRN：可选GPU细化对照

[官方代码](https://github.com/youngLBW/HRN)及
[assets说明](https://github.com/youngLBW/HRN/blob/main/assets/README.md)
核对：单/多视角人脸重建，细节与纹理流程；代码Apache2，依赖BFM资产，
实现仅在Ubuntu/CentOS NVIDIA/CUDA环境测试，含nvdiffrast/PyTorch3D。
它不是已证实Mac原生后端，BFM资产必须单独核许可。
作者明确提示高频displacement渲染效果不一定等于导出mesh细节。
验收必须看实际Blender mesh/法线，不只看作者正面渲染。

### NextFace / FaceVerse：第二梯队

[NextFace](https://github.com/abdallahdib/NextFace)代码GPL3，官方声明CPU/
CUDA，支持拟合几何、diffuse/specular/roughness；依赖Basel模型和较老环境。
CPU支持并不等于Apple Silicon已安装通过，也不代表速度合适。
[Basel官方](https://faces.dmi.unibas.ch/bfm/bfm2019.html)及对应具体版本资产
须核许可，旧BFM非商业条件不能泛化为所有版本已许可。

[FaceVerse](https://github.com/LizhenWangT/FaceVerse)有形状/细节/纹理模块，
新版[v4](https://github.com/LizhenWangT/FaceVerse_v4)链接已提供；根代码许可
为BSD式条款，模型checkpoint/数据授权仍待逐份核查。早期细化含CUDA/
PyTorch3D/StyleGAN编译，不承诺零GPU即插即用。作为GPU对照而非当前默认。

### DetailGen3D：通用几何细化，非身份保证

[官方](https://github.com/VAST-AI-Research/DetailGen3D)输入粗mesh+参考图，
代码MIT；权重/基础模型仍需独立核查。已有Local/Opensource源码。
官方inference load_mesh含无条件`.cuda()`，虽后续有CPU device分支也不能
直接称CPU可运行。它适合独立高质量脸ROI/粗头几何细化的GPU实验，但不能
保证人物身份或自动替换头部。图与粗头必须同角色/视角；不是裁几个部位硬拼。
显存最低值没有本地或官方可靠证据，不填虚构8GB等数字。

### 研究限制与representation差别

[DECA许可](https://github.com/yfeng95/DECA/blob/master/LICENSE)、
[MICA许可](https://github.com/Zielon/MICA/blob/master/LICENSE)、
[INFERNO](https://github.com/radekd91/inferno)明确非商业研究限制。INFERNO的
EMICA组合身份/表情/细节更值得研究，但不能作为开源游戏资产默认自由商用
后端，换成Open FLAME也不解除预测代码/weights限制。

[LAM](https://github.com/aigc3d/LAM)代码Apache2，
[权重](https://github.com/aigc3d/LAM/blob/master/LICENSE_WEIGHT)CC-BY-NC4，
输出animatable Gaussian head。画面好不等于可编辑triangle/quad网格。
官方README提到MeshLAM报告/项目，未确认可安装的公开代码+权重，不把论文
新闻当已可用替代（猜测的aigc3d/MeshLAM地址本轮404）。

## 下一实施验证

1. 当前小满脸部ROI与原图做同相机近景；分开纯BaseColor、clay、normal，
   确认眼睛/嘴的问题分别在哪层，并报告原图脸部实际像素和UV分配。
2. CPU landmark对齐+脸部可见区域mask改进photo-paint；避免原图双嘴和侧缝。
   脸部提高texel分配，处理原图光照污染；未观测侧面不凭补纹理宣称还原。
3. FLAME2023 Open专用可控脸部拟合验证：模型版本/许可/脸部形状约束/
   眼球与嘴独立检查。适用于真实或半写实的范围需评估，Q版大眼不强套真人。
   同一body固定，仅候选头与颈部接合；重接后必须复验UV、蒙皮、表情和接触。
4. CUDA可用再做HRN/DetailGen3D真实对照。输出原图/当前/候选正面、侧面、
   三分之四、眼嘴耳近景及实际GLB/blend，技术与美术结果分别记录。

本轮仅调研与源码核对，没有下载需注册/许可确认的模型，没有接受外部账号
条款或执行未知安装脚本。未修改源图、模型或golden，未新增视觉改善声明。
