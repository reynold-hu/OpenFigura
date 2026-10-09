# 3DGenStudio 3.5.3 → OpenFigura 功能对账矩阵

日期：2026-10-08。来源：对 `~/Desktop/Local/Opensource/3DGenStudio`
（app version 3.5.3）实际源码的全量清点：95 个 MCP 工具（12 组）、
约 150 条 HTTP 路由、4 个 Python 服务、Electron/React 界面、
33 个 ComfyUI 工作流、setup 模型目录。清点条目附 file:line 证据。

状态词（三者不可互替，见 `loop/CONTRACT.md`）：
- `reproduced`：OpenFigura 有同名能力，单测通过；若有真实运行证据会写路径。
- `partial`：存在但覆盖范围更小，缺口在行内写明。
- `absent`：没有对应实现。
- `policy-gate`：与 OpenFigura 的隐私/许可承诺冲突，复现前需要用户决定。

## 1. 网格工具（meshTools.js，14 工具）— 核心重叠区

| Studio | OpenFigura | 状态 |
|---|---|---|
| `auto_uv_mesh`（LSCM/ARAP, :8200） | `mesh uv`（Blender smart_project） | partial：无 chart 优化/LSCM 质量路径 |
| `auto_retopo_mesh`（体壳→remesh） | `mesh retopo`（QuadriFlow） | partial：算法不同，均已声明需重烘焙 |
| `optimize_mesh`（gltfpack） | `mesh optimize`（Decimate） | partial：无 gltfpack 压缩（体积/属性量化未做） |
| `generate_collision`（CoACD 凸分解/box/sphere） | `mesh collision`（每网格单凸包） | partial：凹形覆盖不足 |
| `inspect_mesh`（引擎就绪报告） | `inspect`（结构报告）+ mesh report | partial：无 UV 覆盖率/texel density/流形检测 |
| `segment`（语义部件） | `mesh segment`（连通分量） | partial：96 万三角形实例给出 8,090 噪声组件，语义分解缺失（见 mesh-chain 证据 05-mesh-segment） |
| `repair_mesh`（非流形修复） | — | absent |
| `bake_mesh_maps`（高→低 normal/AO/ORM） | `bake`（CPU normal/AO/albedo） | partial：真实球体及MCP/executor通过；无ORM，scifi首轮覆盖不足 |
| `generate_lods` | — | absent（可用 optimize 手工链式逼近，无命名/层级输出） |
| `transfer_rig`（蒙皮转移，服务端确定性） | `transfer-rig`（重心权重转移） | partial：高低模转移/局域形变通过，不保证语义蒙皮正确 |
| `auto_rig_mesh`（SkinTokens :8300, GPU≥14GB） | `autorig`（MIA CPU） | partial：不同上游，小满手腕仍失败 |
| `convert_mesh_fbx`（Blender FBX + takes） | `export --format fbx` | partial：动画FBX真实产出，多takes编辑未复现 |
| `move_mesh_pivot`（ground/centre，无损节点平移） | `pivot` / `figura_pivot` | partial：静态单场景GLB无损属性平移，CLI/MCP/execute与Blender实证；skin/动画等未支持 |
| `export_mesh` | `export`（含 inspect 闸 + manifest） | reproduced（证据：foundation proof） |

## 2. 生成动作（actions.js，10 工具）

| Studio | OpenFigura | 状态 |
|---|---|---|
| `generate_mesh` Hunyuan/Tripo/Hitem 云 API | `generate`（pixal3d 本地运行时） | partial：本地路线不同；云 API 全部 policy-gate（隐私承诺：无托管服务遥测；数据出境需用户决定） |
| `get_mesh_result`（异步恢复） | workflow 阶段持久化 | partial：阶段可 resume，但无远端任务 id 概念 |
| `generate_image`/`edit_image`（Gemini/OpenAI 模板） | — | policy-gate（同上） |
| `edit_mesh`/`texture_mesh`/`rig_mesh_api`（custom_* API） | `refine_texture` 本地近似 | partial |

## 3. 组织与资产（assets 14 / projects 7 / cards 8 / graph 7）

Task 工作区 + `AssetRef` + `Workflow` 阶段账本覆盖“单资产生产记录”；
全局库、标签检索、看板、节点图、`.3dgp` 项目包导入导出全部 `absent`。
OpenFigura 目前按任务目录组织，无跨项目库。

## 4. 批处理（batch 3 工具）— absent
无变量矩阵、无格点运行、无预算/续跑循环。

## 5. 程序化系统（building 10 / tree 3 / vfx 10）— absent
建筑图编译、树木生成、粒子特效含 Unity/Unreal IR 导出均无对应。
体量各自约等于一个独立子系统。

## 6. 动画/动捕（server :8400/:8401 + 资源库）

| Studio | OpenFigura | 状态 |
|---|---|---|
| Kimodo 文生动作（SOMA-77，Llama-3 门控权重） | — | absent + policy-gate（Meta 许可接受门） |
| MoCapAnything 视频生动作 | — | absent（需 GPU） |
| 动画/动作库（13 组 GLB 剪辑） | `retarget` 接受任意剪辑 | partial：无库管理 |
| 手指姿态修补（handPose） | — | absent |
| 时间轴编辑（dopesheet） | `.blend` 内保留 action（证据：pose-motion 探针） | partial |

## 7. 编辑器 UI（Mesh Editor/Image Editor/Assembly/Board/Wiki）— absent
OpenFigura 是 CLI/MCP 工具层，UI 复现不在当前路线；可动性验收以
`.blend` 打开即有动作时间轴为交付形态（今日已证）。

## 8. ComfyUI 集成（workflows 6 工具 + 33 包内工作流）
`workflow_*` 四个前端动词是**阶段账本**，不是 ComfyUI 执行器：无
inspect/import/run_workflow、无参数注入、无进度 SSE。状态：
partial（语义不同名易混，命名保留但文档写明）。

## 9. 服务与硬件门槛（如实记录）
- mesh-tools :8200：CPU 可跑（trimesh/pymeshlab/coacd/bpy），OpenFigura
  用 Blender 隔离进程覆盖了其中 UV/retopo/collision/optimize/inspect 子集。
- SkinTokens :8300：NVIDIA ≥14GB；Qwen3-0.6B 依赖。
- Kimodo :8400：Llama-3-8B（16GB，门控）+ NVIDIA 检查点。
- MoCap :8401：峰值约 10.4GB VRAM。
- 本机（M5/16GB）当前可诚实执行：mesh 工具、mia CPU autorig、
  native-motion retarget、blender render；pixal3d 无本地运行时。

## 结论（2026-10-08）
2026-10-08 原始清点：95 个 MCP 工具中 reproduced/partial 覆盖 21 个（22%），absent 63，
policy-gate 11（云 API/生成图像/门控权重）。差距集中在：烘焙与蒙皮
转移、语义部件分解、FBX/引擎导出、程序化子系统、库与批处理、UI。
每一项推进需按 `loop/TASKS.md` 逐条以测试+真实产物为凭。

## 晚间补记（同日晚些，追加事实）
- 导出多格式（B 类 #4）已落地并真实运行：FBX（含动画 2.83MB）/OBJ/STL/USD
  全部 exit 0，USDZ 如实报"本 Blender 构建未暴露"。§1 与 §7 中的导出缺口相应收窄。
- `animate` 动词 + 独立 `blender-motion-gate`（真实双向证据入单测）与
  UniMate 适配器合入；Studio 的 auto_rig/Kimodo/MoCap 类功能仍是 absent，
  等待 CUDA 节点后以 L13 实跑数据更新本矩阵。
