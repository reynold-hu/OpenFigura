# 本地高低模烘焙

先准备对齐的 high.glb 与 low.glb，放在任务 artifacts 中。low必须是单网格、
已有UV、未绑定骨架；high可由多个静态网格组成。面数优化或重拓扑后先展开UV，
再烘焙，最后绑定骨架。源图错误、手指缺失、部件粘连不能靠normal贴图修复。

```sh
openfigura bake /absolute/task/path \
  --source high.glb --artifact low.glb \
  --maps normal ao albedo --resolution 1024 --samples 16 \
  --cage-extrusion 0.01 --ray-distance 0.03
```

距离参数是模型世界单位，必须随资产尺寸设置。过小会漏射线，过大可能跨部件
投射错误表面。接口不会自动猜测最佳参数。分辨率64–4096且为2幂，samples1–128；
默认normal+ao，可选albedo保留原高模颜色、不烘光照。

MCP `figura_bake` 使用同名参数；executor步骤`bake`需把高低模型的AssetRef
一并声明，`params`内包含source/artifact和嵌套params。每阶段在独立目录运行。

交付包含model-baked.glb、打包贴图的Blend、每种PNG及bake-report.json。
CPU Cycles执行，原高低模hash、低模面数和UV须保持不变。输出存在即拒绝覆盖。
失败模型隔离，诊断报告可保留；不会覆盖此前人审基线。

验收要检查：UV岛有效面积、贴图射线漏失、脸和衣服对应、normal接缝、glTF中
normal/occlusion/BaseColor引用及真实渲染。报告alpha覆盖含margin而非命中率，
nonconstant不能保证图可用。首轮scifi烘焙的黑底散点是已知失败例，不能交付为
“细节保留”。当前没有ORM/多目标图集/重叠UV自动修复，GPU烘焙尚未实现。

UV工具默认`mode=auto`：技术合格已有图集保留，否则尝试展开。明确更改UV用
`mode=unwrap`或`mode=repack`，间距由`margin_pixels`及`resolution`指定；
默认2px/1024。只保留原图集可选`mode=preserve`，不合格会拒绝，不偷偷重画。
质量检查限单个[0,1]图集，面积5%下限是拒绝极稀疏结果的启发式，不证明无重叠。
scifi继承UV修复对照见handoff-review与桌面scifi-uv-trial；用户视觉接受仍待确认。
