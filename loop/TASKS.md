# 任务与验收表

- [x] L01 Studio 固定版本完整功能矩阵：docs/2026-10-08-studio-parity-matrix.md（95 工具清点，附证据行号）。
- [x] L02 真实执行器：engine.execute 沙箱阶段化运行；180 测试通过；真实证据见 PROGRESS 2026-10-08 晚间条目。
- [x] L03 静态网格工具：已注册并 CLI/MCP 镜像；真实通过 optimize（6.75s）、collision（0.87s）、uv（1.12s）、retopo（voxel 水密管线，QuadriFlow 如实降级并写明）；segment 如实失败（8,090 组件）。证据 `~/Desktop/openfigura-3d-loop-2026-10-08/logs/`。
- [~] L04：transfer_rig 与 CPU normal/AO/albedo真实验证；scifi UV默认重展开破坏图集已修，保留继承UV的1024三贴图及前后真实渲染通过技术复核，美术pending。ORM/多图集等未完。
- [~] L05 Pixal Metal真实生成通过，本地profile已配置；新模型精细脸/口袋未达标。CUDA/其他材质后端/硬件调度未完。
- [~] L06 MIA CPU：scifi52关节结构通过，新半写实小满52关节结构/fit通过；旧chibi未通过。关节数不能替代蒙皮/语义部件/运动质量。
  原高模手腕探针已定位裤腿串指尖权重，原预测6例追溯吻合；见high-skin-audit。
  skin quality 未通过，优先区域约束／独立形变检查。
  表面最短路径试验未解决分界，已留三视角红标局部帧；需独立语义种子审核。
  UV颜色候选计数改善但局部真实帧仍尖刺，未通过；下一步skin质量报告工具。
  只读skin_quality内核完成，32测试+真实导出weights检查；通用GLB读取/三入口/
  固定形变近景尚待接入，不能勾skin quality通过。
  后续GLB读取/engine/CLI/MCP/execute已完成并真实验证；固定形变近景仍未接入。
- [ ] L07 动作接触：scifi 重定向被接触闸持续拒绝。修正循环升级为深度自适应＋
  候选方向探测（logs 15–19）仍不收敛：原始重定向每帧 1000+ 深穿插，两骨 IK
  推挤不足。肩链替代搜索也失败；先审计蒙皮/分区，再试L13 UniMate＋闸筛选，后者尚未证明能解决。
- [~] L08 新generate→inspect→render→autorig真实通过，retarget600秒超时；原mesh-chain接触失败。独立bake/export通过不等于同一可动精细人物链验收。
- [ ] L09 Blender .blend 动作播放及真实前／侧／背面帧，静态和动作主观认可分别记录。
- [ ] L10 Studio其它功能按矩阵实现：项目／资产／编辑／工作台／Comfy工作流／接口。
- [ ] L11 全部适配器的许可证、API／计算依赖和回归样例、包资源检查。
- [ ] L12 最终验收：每项目标文件／命令／实际画面／限制；不足项保留未完成。
- [~] L13 UniMate 后端：代码侧完成——adapter/预检(≤71骨/单根/重名/蒙皮)/
  animate 动词(逐次 NC 许可确认+账本)/独立 motion-gate(CLI+MCP+execute 三镜像)；
  真实 Blender 正反证据入测试(204 passed)。待：CUDA 节点接上后跑
  scifi "An object walks forward." ×3 全闸验证，对照 retarget 深穿插负结果。
- [ ] L14 CUDA 速度基准矩阵（口径见 docs/product.md「Speed stance」）：GPU 节点
  到位后第一时间跑 backend(pixal3d/TRELLIS/Hunyuan2.1/UniMate) × 显存档位 ×
  固定 seed，各阶段 wall time 由账本记录并发布；对外宣传引用速度数字必须以本
  矩阵实测值为来源。

## 本轮执行信息

- [~] 降面可靠性：默认exact seam weld、拓扑不回归与rawGLB有限数值闸已实现；
  真实sphere/plane/共享instance及NaN反例已验证。小满因新增58重复面拒绝。
  下一步独立repair再复验，不能把裂纹消失的诊断PNG当完整通过。

开发分支 codex/3d-loop，起点8127434；用户未跟踪golden和研究文件保持独立。
TDD默认单元测试不依赖Blender/CUDA；真实Blender与算法测试存主仓库`.local/runs/<批次>/`，gitignore并更新catalog。旧桌面路径按catalog映射读取。
