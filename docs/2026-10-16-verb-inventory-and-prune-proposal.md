# OpenFigura 动词清点与建议剔除清单 — 2026-10-16

触发：Tripo 公开功能调研 §13.4 的剔除结论（evidence:
`.local/runs/2026-10-16-tripo-studio-review/11-full-bundle/`）。本文是
**清点 + 建议**；代码一行未删，等人类拍板。

方法：从 `cli.py` 解析出 33 个 CLI 动词（本报告生成时点；`print-check` 为随后新增，见 §4），逐一核对三处证据：`tests/` 的
覆盖、`PROGRESS.md` 的记载、`.local/runs/` 的真实运行目录。PROGRESS 命中
数是方向性信号（`rig` 会误配 rigging/right），结论以人工核对为准。

## 1. 全量动词表

结论列：`keep` 保留 / `keep-exp` 保留且明确实验性 / `gate` 保留但受许可或
策略门 / `prune-proposed` 建议剔除（等拍板） / `dormant-proposed` 建议保留
但标注休眠。

| 动词（CLI / MCP） | 用途 | 证据（最近） | 结论 |
|---|---|---|---|
| `new` / `figura_new_task` | 建任务 + 暂存输入 | 全链路使用中 | keep |
| `generate` / `figura_generate` | 图→GLB（pixal3d） | PROGRESS 多篇；golden-run 生成任务 | keep |
| `preflight` / `figura_preflight` | 输入门禁（本轮加 symmetry） | `tests/test_preflight.py`、真实 matte 实测 | keep |
| `print-check` / `figura_print_check` | 本地可打印性报告（新增） | `tests/test_printability.py`、`.local/runs/2026-10-16-print-check/` | keep（本批新增） |
| `render` / `figura_render` | 中性多视图渲染 | 每轮验收的默认证据 | keep |
| `inspect` / `figura_inspect` | 结构报告 + 导出闸 | 全链路使用中 | keep |
| `export` / `figura_export` | 交付（本轮加 fbx 预设） | `2026-10-16-borrow-batch/` | keep |
| `mesh` / `figura_mesh` | segment/optimize/retopo/collision/uv | 2026-10-08/09 多次真实运行（本轮加 use_case） | keep-exp（segment 无语义是已知限制） |
| `pivot` / `figura_pivot` | 资产原点重定 | `.local/runs/2026-10-09-studio-pivot-tool/` | keep |
| `bake` / `figura_bake` | 高→低法线/AO 烘焙 | 真实球体 + 2026-10-10 真实链条 | keep |
| `workflow-*` / `figura_workflow_*` | 阶段账本（submit/status/cancel/resume） | `tests/test_workflow_frontends.py`、foundation proof | keep |
| `execute` / `figura_execute` | 动词的持久阶段执行 | `test_execution*.py` 多处 | keep |
| `backends` / `figura_backends` | 后端探针 | 每台机器诚实可用性 | keep |
| `syscheck` / `figura_syscheck` | 环境自检 | `test_syscheck.py` | keep |
| `presets` / `figura_presets` | use_case 预算表（本批新增） | `tests/test_presets.py` | keep |
| `autorig` / `figura_autorig` | 神经绑骨（MIA） | Windows/CUDA 大批 PROGRESS；bunny/小满通过 | keep-exp |
| `retarget` / `figura_retarget` | 动作迁移 + 接触门 | 2026-10-08 起多篇；修正限制已记录 | keep-exp |
| `transfer-rig` / `figura_transfer_rig` | 骨骼+权重转移 | `.local/runs/2026-10-09-uv-skin-trial/` | keep-exp |
| `rig` / `figura_rig` | Rigify 校准绑骨 | 真实 chibi + Godot 证明 | keep-exp |
| `skin-check` / `figura_skin_check` | 权重只读诊断 | `.local/runs/2026-10-09-skin-check-tool/` | keep |
| `skin-probe` / `figura_skin_probe` | 固定姿态形变诊断 | `.local/runs/2026-10-09-skin-probe-tool/` | keep |
| `animate` / `figura_animate` | UniMate 文生动作 + 区域门 | Windows 多次交付；NC 许可门 | gate |
| `face-landmarks` / `figura_face_landmarks` | 478 点 + blendshapes | 2026-10-08 起；mediapipe extra | keep-exp |
| `face-mask` / `figura_face_mask` | 面部 ROI 掩码 | face chain 验证 | keep-exp |
| `head-roi` / `figura_head_roi` | 风格化角色头部 ROI | 同上 | keep-exp |
| `face-expression-report` / `figura_face_expression_report` | blendshape 排序报告 | 2026-10-08 verb chain | keep-exp |
| `expression-align` / `figura_expression_align` | MakeHuman face units 注册 | 验收门 + 人体批准记录 | keep-exp |
| `expressions` / `figura_expressions` | ARKit morph 写入 | GLB 通道数验证 | keep-exp |
| `refine-texture` / `figura_refine_texture` | 参考图像素投影 | 多次实验 + ROI 门控 | keep-exp |
| ~~`set-style` / `figura_set_style`~~ | ~~记录像素风格 spec~~ | 无消费者、无渲染器 | **pruned 2026-10-16**（用户批准，整栈删除） |
| ~~`project-style` / `figura_project_style`~~ | ~~读 style spec~~ | 同上 | **pruned 2026-10-16** |

后端层面：注册中的 `pixal3d / blender-* / gltf-pivot / mediapipe-face /
mia / native-motion / photo-paint / rigify / unimate` 全部有测试与至少一次
真实运行或明确的不可用原因（`openfigura backends` 诚实报告），无死后端。

## 2. 建议剔除清单（按风险分级）

**A. 已执行剔除（2026-10-16，用户拍板"都可以"，选择删除）**

1. ~~`set-style` / `project-style` + `core/style.py`（StyleSpec）+ 2 个前端
   入口 + `test_project_style.py` + `test_asset_contracts.py` 中
   style 相关断言。~~
   **已删除**：`core/style.py`、`Task.record_style`、engine 两个函数、
   CLI/MCP 两个入口、`test_project_style.py` 及 `test_asset_contracts.py`
   的 style 用例；`docs/asset-workflow-foundation.md` 记录移除。
   理由：**唯一无消费者的公开接口**（只写账本，无任何输出路径读取，
   像素生成器不存在），留着会误导 agent。

**B. 保留但建议降级表述（不删代码）**

2. `mesh segment`：拓扑分割已被实测证明给不出语义部件（8,090 噪声块，
   PROGRESS 2026-10-08）。保留作连通分量工具，但 usage/MCP 描述建议
   直接引用实测结论，防误用。
3. `animate`（UniMate）：NC 许可门，保留现状（gate）。

**C. 已在文档/路线图正式剔除（本轮执行，不涉及代码）**

见 `ROADMAP.md` 新增的 Rejected 一节：Agent 面板/画布、云精修、
云动作库、Video-to-Motion、Credits 计费、遥测/会话回放、DCC 插件矩阵、
多视图输入、文本生 3D（除非本地后端出现）、8K 纹理（先证 4K）。

## 3. 数字口径

- 当前 **32 个 CLI 动词 / 32 个 MCP 工具**，全部镜像（审计快照为 33，随后
  删除 2 个 style 动词、+1 `print-check`）。另有 5 个 mesh 操作、6 个 export
  格式分支。
- 真实验证目录（`.local/runs/`）：2026-10-09 一批 20+ 个工具级目录 +
  foundation proof + 本轮 borrow-batch。
- 630 测试（本报告生成时点，`python -m pytest tests -q` 全绿）。
