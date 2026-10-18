# 脸部纹素密度审计 + 面部 ROI 精修 A/B — 2026-10-17

配套文档：`docs/2026-10-17-face-quality-rubric.md`。证据目录
`.local/runs/2026-10-17-face-ab/`（审计脚本 `texel_audit.py`、A/B 拼图、
`face-ab-report.json`、`texel-density.json`）。全部本机 CPU 执行。

## 1. 纹素密度审计

方法：读取 GLB 第一个 primitive 的 `POSITION`/`TEXCOORD_0`/索引，逐三角形
算 3D 面积与 UV 面积，用内嵌 baseColor 图尺寸换算
`texels_per_meter = sqrt(uv_area × atlas_px / 3d_area)`；头部 = Y 轴最高
18% 高度带；**按 3D 面积加权**（中位数同时给出）。

| 资产 | atlas | 头部 texels/cm | 身体 texels/cm | 头/身比 | 头部 UV 面积占比 | 头部 3D 面积占比 |
|---|---|---|---|---|---|---|
| silver-scarf | 2048² | 11.15 | 11.16 | **1.004** | 14.83% | 14.70% |
| xiaoman-regen | 2048² | 13.37 | 13.24 | **1.012** | 21.17% | 20.76% |

结论：

- 两个生成资产的 UV 分配**基本均匀**，没有刻意为脸加权；头部 UV 占比与
  3D 面积占比几乎一致。
- 绝对密度约 **11–13.5 texels/cm**：12 cm 高的脸约 130–160 px。
- silver-scarf 的参考图脸只有 **99×117 px**（校准视图 1022²）——
  **2048 atlas 已经不是瓶颈，输入像素才是**。4K atlas 只会把线性密度翻倍，
  但不会凭空产生参考图没有的五官细节。
- 只有在"参考图脸足够大"（如 head-sculpt 实测 432 px）或做特写交付时，
  4K/第二材质才值得；当前不升级。

## 2. 面部 ROI 精修 A/B（silver-scarf）

链路（全部现有动词，无新模型）：
`face-landmarks --image input/view.png` → `face-mask` → `refine-texture
--roi-mask input/face-roi.png --strength 1` → 两个 artifact 同机位渲染
（`--facing 180`）。

- 参考脸 bbox：99.2×117.1 px（1022² 校准视图）；人脸 ROI 占 atlas
  1.67%（trust map >0.5 面积）。
- 像素对比（`face-ab-report.json`）：头带裁切内 changed>2 的像素
  **front 4.78%**、**three-quarter 3.55%**；头部平均绝对差 1.44 / 1.11，
  变化集中在脸（全主体 1.35% / 1.01%）。
- 目视（`face-ab-front.png`，左原图/右精修）：眼睛、鼻翼、嘴部明显更清晰，
  皮肤不再"糊成一片"；未见明显接缝。**人工评分仍 pending**，按 rubric 走。

## 3. 决策

1. **暂不做 4K/第二材质**：对当前全身立绘，ROI 投影的收益/成本更高；
   4K 等有高分辨率脸部案例且评分证明"纹理受限"再上。
2. **优先做**：脸部 ROI 投影（已有链路 + 本次 A/B）、面部裁切/放大输入、
   高分辨率头部参考图；
3. 4K 触发条件（写进评审）：参考脸短边 ≥200 px，且 2048 下评分单项
   "D. 面部贴图" ≤12 分。
