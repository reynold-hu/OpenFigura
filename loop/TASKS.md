# 任务与验收表

- [x] L01 Studio 固定版本完整功能矩阵：docs/2026-10-08-studio-parity-matrix.md（95 工具清点，附证据行号）。
- [x] L02 真实执行器：engine.execute 沙箱阶段化运行；180 测试通过；真实证据见 PROGRESS 2026-10-08 晚间条目。
- [x] L03 静态网格工具：已注册并 CLI/MCP 镜像；真实通过 optimize（6.75s）、collision（0.87s）、uv（1.12s）、retopo（voxel 水密管线，QuadriFlow 如实降级并写明）；segment 如实失败（8,090 组件）。证据 `~/Desktop/openfigura-3d-loop-2026-10-08/logs/`。
- [ ] L04 原始高模→低模的材质／normal／AO烘焙与蒙皮转移。当前全部 absent；transfer_rig 是最高优先。
- [ ] L05 神经生成／材质后端能力与硬件调度：可用则执行，不可用则给出真实原因。
- [~] L06 自动骨架／解剖约束：scifi 低模经 MIA CPU 自动骨架**通过**（52 关节，12.75s，无手工坐标，fit/skin/原图哈希三重校验；证据 13-autorig-scifi.json）。小满仍无通过项。
- [ ] L07 动作接触：scifi 重定向被**接触闸拒绝**（第 1 帧 left hand 间隙不足，见 14-retarget-scifi 沙箱 provenance）。说明闸有效，不碰撞交付未达成；需增加区域／时间采样与碰撞修正。
- [~] L08 完整主链：mesh-chain 任务内 inspect→optimize→(segment fail)→retopo→uv→autorig→retarget(fail) 全部阶段化串联、同任务关联；缺 generate（本机无运行时）与 export 通过项。
- [ ] L09 Blender .blend 动作播放及真实前／侧／背面帧，静态和动作主观认可分别记录。
- [ ] L10 Studio其它功能按矩阵实现：项目／资产／编辑／工作台／Comfy工作流／接口。
- [ ] L11 全部适配器的许可证、API／计算依赖和回归样例、包资源检查。
- [ ] L12 最终验收：每项目标文件／命令／实际画面／限制；不足项保留未完成。

## 本轮执行信息

开发分支 codex/3d-loop，起点8127434；用户未跟踪golden和研究文件保持独立。
TDD默认单元测试不依赖Blender/CUDA；真实Blender与算法测试另存桌面证据目录。
