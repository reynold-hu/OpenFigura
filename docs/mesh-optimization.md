# 降面与拓扑验收

```sh
openfigura mesh /absolute/task/path --operation optimize \
  --artifact model.glb --params '{"ratio":0.08,"weld_seams":true}'
```

默认先精确合并重合顶点（距离0，非近似焊接），再Blender Decimate。原输入为
私有快照；修改的是候选。共享网格实例先复制成各自数据块。
这能避免glTF为UV/法线拆开的顶点被分别降面、在表面打开大量缝隙。
`weld_seams`必须是真正Boolean；false用于比较，仍受同样的拓扑拒绝规则约束。

报告给出original/prepared/result的位置聚类边界、非流形边、退化/重复面数量。
合并前后核对存活面的坐标、全部UV层、材质索引及绕序，记录删除数量和bounds。
干净封闭输入不能被合并步骤破坏；降面后任一缺陷计数增加即拒绝，GLB不导出。
失败diagnostic保留；直接engine调用的失败GLB/Blend也隔离到rejected。

数值预检在Blender导入前执行，防止导入器将NaN洗成普通数值。限单JSON+单BIN
的嵌入式GLB；检查POSITION/TEXCOORD浮点base及sparse值、偏移/stride/view界限，
拒绝非有限值及外部/多buffer、Draco/meshopt、未知chunk。它不是完整glTF验证器。
导入后还检查坐标/全部UV层有限性；Blender操作异常保留机器可读失败报告。

精确合并可能连接有意接触的表面，删除原始缺陷面可能开放原本损坏的源。
法线和降面后的UV映射可能改变；counts/bounds不能证明自交、封闭体积、形状误差
或美术通过。仍需真正的repair、烘焙、渲染和动作闸，不能用“顶点变少”替代验收。

本地真实证据均在主仓库`.local/runs/`：

- `2026-10-09-weld-optimize/`：同镜头纹理/clay试验显示裂纹明显消失，但候选
  仍422边界、2502非流形边、58重复面，**仅诊断候选**。
- `2026-10-09-optimize-tool-verify/`：生产球体528→264面通过、开放平面通过；
  小满重复面0→58拒绝，关闭合并则边界0→84873拒绝，两者均未发布GLB。
- `2026-10-09-optimize-review-verify/`：共享实例及原始NaN/Inf样本。初次
  post-import检查漏掉NaN的反例保留，final/completion报告证明导入前拒绝修复。

小满精细脸部、材质、正规拓扑修复与不碰撞动作仍未验收；不会将试验PNG冒充
生产可交付模型。CLI/MCP/execute统一调用核心mesh接口，无独立前端算法。
