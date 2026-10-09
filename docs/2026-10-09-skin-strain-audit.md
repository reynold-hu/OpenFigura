# 固定手腕探针的三角面拉伸定位

本轮只定位严重形变面，不修权重、不删面、不改变碰撞区域。源blend保持，
skin/collision acceptance false、visual pending。

## 实际检查

输入是skin-probe第二次真实高模阶段的诊断blend，先frame1取基线，再frame2
左腕、frame3右腕的独立30°姿态。对每个原三角形的三条边，计算rest和posed
世界长度。筛选规则固定为rest边长>1e-6、伸长比>10且绝对增长>0.002世界
单位；这是拉伸诊断，不是碰撞判定或新的碰撞margin。

| 探针 | 至少一条严重拉伸边的三角面 | 所有合格边最大比值 | 所有边最大增长 |
|---|---:|---:|---:|
| Left wrist frame2 | 112 | 19.4458 | 0.0355812 |
| Right wrist frame3 | 83 | 18.1803 | 0.0343667 |

最高增长样本的三角面中有Leg／finger主导标签交错，报告保留全部顶点权重、
原/姿态位置、三边长度和三角编号。样本索引属于导入Blender mesh，非原GLB。
它们不是语义真值，也不是已确认几何融合的证据。

渲染使用同一真实blend：新增红色覆盖面，偏向相机0.0002世界单位以减少
z-fighting，原mesh和材质不修改。每侧rest/posed两个768×768、CPU16sample
近景，root实看四帧。红面集中在指尖旁的裤面尖刺，静态时小片、转腕后拉长。
overlay是注释，不是修复后的模型，也不是生产输出。

两侧原source triangles尚可能全为裤料，或跨实际皮肤／裤料界面；主导骨
标签不能分辨。没有独立语义/UV角点核验前，不能因伸长就断言手裤粘连，
不能盲目切边、删面、降低skin阈值。先对严重面及相邻表面建立可核对的
语义连贯区域，判断该改权重还是拆几何，再在相同探针/近景下复验。

## 证据

主仓库`.local/runs/2026-10-09-skin-strain-audit/`。
`strain.py`和`render.py`实际Blender调用均exit0；前者report.json和每帧npz
保留精确样本、位置和选择；后者render-report.json及四张marked PNG。
命令、wall及源hash见ledger；manifest/catalog记录产物，原blend SHA前后保持。
未重复生成、绑定、IK或同色阈值网格，未发布修复模型；生产代码未变，本轮
不重跑既有568单测。此前skin工具pass不等于模型通过，本轮也没有模型pass。
