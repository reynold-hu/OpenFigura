# 资产评估体系调研与 agent 预评分卡 — 2026-10-17

> **定位**：开源项目（AGPL-3.0）、本地、CPU-first。本文调研"游戏/建模/3D 打印
> 行业里现成的开源评估与校验体系"，并定义 OpenFigura 自己的 **agent 预评分卡**。
> 预评分只回答"离可评审交付还差什么"，**不评价美丑**；美学与五官相似度仍归
> 人工 rubric（`docs/2026-10-17-face-quality-rubric.md`）。

## 1. 开源生态：能拿什么、不能拿什么

| 项目 | 许可证 | 能提供 | 我们的决定 |
|---|---|---|---|
| **Khronos glTF-Validator** | Apache-2.0 | glTF 2.0 规范级校验（结构、访问器、扩展） | **已接入（外部 Node，可选）** |
| **glTF-Transform** | MIT | inspect / 优化 / 格式转换 | 可选参考；不引入依赖 |
| **trimesh** | MIT | watertight/体积/组件/自交等几何检查 | **已接入（外部 Python，可选，300k 面预算）** |
| **Open3D** | MIT（仓库标注 NOASSERTION，需按 LICENSE 复核） | Chamfer/F-score/法线一致性等 | 研究/可选，不默认引入 |
| **PyMeshLab** | **GPL-3.0** | SDF（壁厚代理）、拓扑/距离滤波 | **仅外部进程**（已用于 wall thickness 代理），不 vendor |
| **scikit-image** | BSD-3-Clause | SSIM/PSNR 等图像质量 | 渲染回归的可选依赖 |
| **imagehash** | BSD-2-Clause | 感知哈希（回归去重） | 渲染回归的可选依赖 |
| **LPIPS (PerceptualSimilarity)** | BSD-2-Clause | 感知相似度 A/B | GPU/可选，需权重 |
| **CLIP** | MIT | 图文语义相似度 | GPU/可选，不默认 |
| **IQA-PyTorch (pyiqa)** | **PolyForm Noncommercial** | BRISQUE/NIQE/CLIP-IQA 等无参考质量 | **拒绝**：非商用许可与开源项目的商用场景冲突 |
| **ULIP / OpenShape / Uni3D 类** | 需逐个复核 | 3D 语义对齐指标 | 仅研究跟踪，不进产品 |
| **Khronos glTF Asset Creation Guidelines** | 文档 | 资产制作与校验清单 | 作为检查项来源（概念） |
| **Blender 3D Print Toolbox** | GPL-2.0+（Blender 插件） | 壁厚/悬垂/自交等打印检查 | 仅作为检查项参考，不复制代码 |
| **Unity/Unreal 资产校验** | 引擎/商业许可 | 平台内校验 | **不复用**（非开源、与本地工具层无关） |

结论：**规范级校验与几何检查可以借鉴，感知/语义指标依赖 GPU 与权重，暂不进
默认路径**；任何非商用或引擎绑定许可都不引入。`score` 全部是 stdlib；
`evaluate` 可选调用两个外部运行时（不下载、不 vendor、不进项目依赖）：

```sh
export OPENFIGURA_GLTF_VALIDATOR_MODULE=/abs/path/node_modules/gltf-validator
export OPENFIGURA_TRIMESH_PYTHON=/abs/path/venv/bin/python
export OPENFIGURA_TRIMESH_MAX_FACES=300000   # 可选，默认 30 万面
openfigura evaluate TASK
```

| 外部项 | 真实结果（2026-10-17） | 备注 |
|---|---|---|
| glTF-Validator 2.0.0-dev.3.10 | 四个资产全部 0 errors；icosphere/bunny 各 1 info | 规范级，不代表画质 |
| trimesh 5.1.1 / networkx | icosphere：watertight True、1 组件、Euler 2；bunny：False、5 组件 | 精确位置焊接后检查；与 printability 的 shell 定义可能不同 |
| trimesh 预算 | scifi 958,816 面、silver-scarf 988,564 面 → **skipped（>300k）** | 避免 1M 面把评测挂住；先 optimize/retopo |
| 计时 | icosphere 0.23s、bunny 0.41s（全报告）；scifi/silver-scarf 跳过时约 2.7s | 均为本机 CPU |

## 2. OpenFigura 预评分卡（`score` / `figura_score`）

命令：

```sh
openfigura score TASK
openfigura score TASK --params '{"profile": "print", "build_volume_mm": [256,256,256], "face": true}'
```

输出 0–100 的 **ready-for-human-review** 评分，五项子分（公式写在
`core/scorecard.py`，全部确定性）：

| 子分 | 权重（default / print） | 内容 |
|---|---|---|
| `structure` | 30% / 25% | inspect 通过、法线/UV/PBR、零面积/重复面扣分 |
| `evidence` | 25% / 20% | 输入、preflight、generate、inspect、render、export 的账本覆盖 |
| `input` | 20% / 10% | preflight 结果、对称性、可选人脸像素/触边 |
| `printability` | 15% / 35% | 开边/非流形/退化面、可选打印平台适配 |
| `delivery` | 10% / 10% | export 记录、provenance、导出哈希 |

- 总分 ≥80 且 `structure` ≥80 且 `evidence` ≥80 → `ready_for_human_review`，
  否则 `needs_work`；**没有任何美学判断**。
- `human_review.status` 永远是 `pending`；rubric 文档是唯一的美学评分入口。
- 输出 `<task>/scorecard.json` 并记入账本（step=`score`）。
- CPU-only，无网络、无新依赖。

### 真实资产冒烟基线（不是质量结论）

| 资产 | overall | structure | printability | input | evidence | 读法 |
|---|---|---|---|---|---|---|
| closed icosphere | 59 | 100 | 100 | — | 0 | 只有几何文件，无生产账本 |
| bunny | 56 | 100 | 88 | — | 0 | 拓扑有轻微缺陷 |
| scifi | 34 | 70 | 30 | — | 0 | 95.8 万面、非流形/退化拖低 |
| silver-scarf（精修任务） | 53 | 70 | 30 | 90 | 30 | 输入质量高，但账本不完整 |

这些数字用于**趋势与回归**（闭合 > 开放、非对称 < 对称、小脸 < 大脸），
不是"这个模型好不好看"的结论。

## 3. 测试集合

- `tests/test_scorecard.py`（8 个）：结构/开放网格/对称输入/打印平台/人脸
  信号/参数校验/CLI-MCP 镜像/账本与报告写入。全部 stdlib，无模型依赖。
- 相对断言而非魔法数字：闭合网格 printability 高于开放网格；非对称输入
  input 分更低；小脸/触边扣分；未知参数 fail closed。
- 真实资产冒烟结果在 `.local/runs/2026-10-17-scorecard/`（不提交）。
- 后续（需要人类或 GPU）：渲染回归（imagehash/SSIM），LPIPS/CLIP 语义
  对比，人工 rubric 基线。

## 4. 不做什么

- 不做"全自动美术评分"：无参考质量指标与偏好模型都有许可/算力/偏差问题；
- 不把预评分当验收：`visual_approval` 仍然只属于人；
- 不引入非商用许可（pyiqa）或引擎绑定校验器。
