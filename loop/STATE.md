# OpenFigura 3D 完整验收状态

日期：2026-10-08（Asia/Shanghai）。状态：进行中，尚未达成最终验收。

## 用户验收目标

1. 参考图到精细 3D 模型，几何与脸／衣物材质要经真实渲染验收。
2. 部件拆解、骨架定位、蒙皮与可动模型。
3. 指定动作的穿插／接触检查及修正，失败禁止交付。
4. Blender 中打开真实 .blend，时间轴可播放，并提供动作帧证据。
5. 3DGenStudio 全功能按一份固定版本矩阵独立复现；不复制受限代码。

## 当前事实

- 起点：8127434；本轮新增执行器／网格工具／前端镜像后 **180 单测通过**
  （`python -m pytest tests -q`，Python 3.14 venv）。三次小提交（DCO）。
- `engine.execute` 已实现：动词在 `stages/<id>/` 沙箱内真实运行，输入按
  hash 校验，输出为已验证 AssetRef，pass/fail 同时写阶段库与 provenance。
- 网格工具已在真实 Blender 跑通：scifi-stride 958,816→95,881 tris（6.75s）、
  collision（0.87s）、链式 inspect 均 pass；segment 如实失败（8,090 组件，
  max_parts 保护，未写产物）。证据 `~/Desktop/openfigura-3d-loop-2026-10-08/logs/`。
- 动作链真实证据：executor retarget 通过（MIA bunny + Mixamo clip，31 帧
  区域接触校验）；打开产出 .blend 探针：action 帧区 1–31、520 通道、
  11 根肢骨在 8/16/24/31 相对第 1 帧全部位移；render frame 1 vs 16 像素差
  179,634/648,000。即"能在 Blender 里动起来"已有客观证据（主观认可待用户）。
- Studio parity 矩阵已落地：95 个 MCP 工具，21 项 reproduced/partial，
  63 项 absent，11 项 policy-gate（云 API／门控权重）。见
  `docs/2026-10-08-studio-parity-matrix.md`。
- 自动骨架：MIA CPU Bunny 通过、小满手腕失败；尚无新的神经自动骨架通过项。

## 当前推进

- L04：高→低烘焙、蒙皮／骨架转移（transfer_rig）、FBX／pivot 导出缺口最大。
- L06：需要新模型或算法改进才能拿下小满自动骨架。
- L07：区域／时间采样覆盖仍受限于整数帧＋部分区域。
- 本机无 pixal3d 运行时；Windows CUDA 节点信息仍待用户回答。

## 依赖与风险

- Windows CUDA 节点信息待用户回答（显卡／显存／访问方式）。Mac 可继续CPU／Metal工作。
- SkinTokens 上游至少14GB NVIDIA，Hunyuan2.1纹理上游21GB；不能承诺16GB Mac跑所有模型。
- “不碰撞”必须说明模型、片段、区域和采样范围；未覆盖的检测不写 pass。
- “全部Studio功能”覆盖范围包含工作台与其它功能，按矩阵逐项验收，不以一个Demo代替。

## 接续工作

每轮从 TASKS.md 首个未完成项继续；每项代码有失败测试、修复、测试与真实文件证据。
无需重复请求已授权开发确认；硬件、密钥或外部访问缺失时记录原因并推进独立任务。
