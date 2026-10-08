# 修复试验与下一步架构

全部候选在主仓库`.local/runs/`，原模型hash不变，没有合格人物交付。

- `2026-10-09-topology-repair-trial/`：删除773面，仍2493非流形边、443边界。
  边界多为开放链和分叉，不能盲填洞；BMesh保留custom-normal标记却改变实际
  法线，恢复后仍有量化误差，未过严格属性闸。
- `2026-10-09-pymeshlab-probe/`：Python3.14/PyMeshLab2025.7.post1原生ARM64、
  CPU tetra与wedge UV smoke通过。独立venv位于Local/Opensource，不改core。
  wheel hash与官方PyPI匹配，安装包许可GPL-3.0。
- `2026-10-09-pymeshlab-face-mask/`：一次Remove Faces保留了原始面ID对应。
  删除5125面（0.54063%，面积0.11425%）；预清理后非流形边2502→0，但边界
  443→7327、组件49→133、非流形顶点376→1868。322重叠面均相反绕序，288
  有不同UV。结果partial，不能当作纯噪声无害删除或闭合修复。
- `2026-10-09-glb-face-index-verify/`：索引编辑器只追加新index数据，原BIN
  前缀/accessors/views/PBR/图像/UV/法线/nodes/scenes不变，真front render保住
  外观（root看图）。仍为开放面诊断候选；再降面因新重复面0→22拒绝，无低模。

直接GLB与Blender对源退化面的计数口径不同；预清理后计数一致，不混淆相减。

`core.glb_faces.prune_faces`是内部索引编辑器，不是repair CLI/MCP后端。只支持
静态indexed TRIANGLES、无sparse/压缩indices、单嵌入buffer，默认primitive删面
预算1%。拒绝空/重复/越界ID、源别名、既有/悬空symlink输出；原子发布不覆盖
竞争写入。保留原未引用顶点及旧index字节，不是数据抹除器；repair_complete
始终false，caller必须审计删面、UV冲突、部件和真实拓扑。

三条路线尚未达到正式验收，本轮停止同族删面/Decimate试错。下一步先评估
薄层壳结构、属性/边界约束简化算法与目标实际面数；不能用拆vertex IDs伪造
几何缺陷归零。体素重建须单列原图重烘焙及脸/手/衣服损失验收，不能声称原
结构保留。语义拆解、蒙皮和动作闸继续独立验收。

研究依据：[PyMeshLab仓库](https://github.com/cnr-isti-vclab/PyMeshLab)、
[官方repair文档](https://pymeshlab.readthedocs.io/en/latest/filter_list.html#meshing-repair-non-manifold-edges)。
没有复制3DGenStudio CommunityLicense源码。
