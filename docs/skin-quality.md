# 蒙皮质量检查：只读内核

已提供 `skin-check` CLI、`figura_skin_check` MCP 和执行器同名步骤，共用engine。
GLB读取器与只读内核完成；固定姿态形变与近景报告尚未接入。
它不替代接触闸或美术认可，也不自动修正权重。

## 工具入口

```sh
openfigura skin-check <task> --artifact model.glb --config skin-config.json
```

config需要显式`families`和`pairs`，还可包含`mass_threshold`、`sum_tolerance`、
`sample_limit`。骨名应使用该skin真实名字；例如：

```json
{"families":{"hand":["mixamorig:LeftHand","mixamorig:LeftHandIndex3"],
             "leg":["mixamorig:LeftUpLeg","mixamorig:LeftLeg"]},
 "pairs":[["hand","leg"]]}
```

这只是小示例，不代表完整手指族；调用方应包含需要检测的所有骨骼。
MCP传`task_root, config, artifact`；execute params传`config, artifact`，输入是
hash验证的model AssetRef。Python调用execute时也应使用JSON数组，不能传tuple。

`status=pass`只表示检查运行与报告发布完成。必须读取`assessment`；它可为
suspicious或invalid_weights。接受标记始终false，不产生动画或修正模型。
报告位于`artifacts/<model-stem>-skin-check.json`，既有报告不覆盖；execute
沙箱允许用同输入/config复用验证过的报告缓存。

## GLB支持范围

GLB2、asset.version2.0、单个嵌入BIN。遍历**所有携带skin的节点**，包括
不在active scene的节点；实例分别报告，顶点统计是各节点primitive之和。
每个报告标注node/skin/mesh/primitive，样本ID是该primitive的本地顶点索引。
按正确skin局部joint索引映射唯一非空骨名，重复有效影响聚合不归一化。

支持连续配对的JOINTS_n/WEIGHTS_n多个sets；joints为UINT8/UINT16 VEC4，
weights为FLOAT32或normalized UINT8/UINT16 VEC4；POSITION为FLOAT VEC3。
验证accessor/view引用、counts、stride、alignment和范围。
压缩、sparse、外部buffer、GPU-instanced skin或不支持的类型明确拒绝。
不检查bind matrix、姿态、POSITION数值质量、材质或全身碰撞，也不推断语义。

engine私有输入快照、前后SHA与原输入复核；报告原子发布，竞争文件不覆盖，
文件替换/hash变化拒绝，输出声明前再次核对。缓存包含GLB reader、skin parser
和diagnostic kernel hash。Windows尚未实机验证。

## 接口

输入是一次性可迭代的逐顶点 `{bone_name: weight}` 记录、显式且互不重叠的
骨族，以及需要检查的骨族对。示例：

```python
from openfigura.core.skin_quality import analyze_weights
report = analyze_weights(
    [{'finger': 0.54, 'thigh': 0.30, 'knee': 0.16}],
    {'hand': ['finger'], 'leg': ['thigh', 'knee']},
    [('hand', 'leg')],
)
```

检查骨族总质量，而非只看主导骨；同一骨族对质量都**严格大于**默认0.1时
记录混合。显式骨族配置需要调用方审核，不是自动语义分区。阈值只用于
诊断权重质量，与2mm碰撞间隙无关。

统计未赋权、负权重、非有限／无法表示值、权重和偏差、未映射正权重、
骨族冲突，以及检查覆盖计数。负／非有限行先报坏值，随后跳过权重和、
未映射、冲突检查；零质量单列为未赋权。不能把跳过后为0的统计解释成
这些项全部检查并通过。聚合溢出也报告invalid。

`assessment` 是 `unavailable`、`invalid_weights`、`suspicious` 或
`no_flagged_conflicts`。最后一种仅表示指定规则没发现问题。
`skin_quality_accepted=False`、`collision_checked=False` 始终保留。
不会重归一化输入，不会改配置；样本ID为记录输入顺序，不自动对应mesh ID。
默认每对保存20个样本，配置上限1000；全量冲突计数不截断。

## 已验证的真实数据

批次 `.local/runs/2026-10-09-skin-quality-kernel/`。
独立32项测试与review验证输入保存、坏值、覆盖、重复/交叠配置拒绝、阈值边界、
流式数据和有界样本。review找到超大整数崩溃，新增4项红测后修复，复审无blocker。

真实新小满原rig GLB SHA
`2ec138122c3dba8de416a540831aedd5fc7e48677a81cd00f159c3a67656d0dc`
原始JOINTS_0/WEIGHTS_0读取后，对698,962导出顶点运行内核：LeftHand/
LeftLeg混合671、RightHand/RightLeg527、两条跨侧对0，状态suspicious；数值
权重有效不改变这个结论。初版约1.83s，复审版时间见real-report-reviewed。
源hash保持、没有Blender新形变或动画交付，visual pending。

这个 `verify_real*.py` 只支持本输入的UINT8 joints/FLOAT weights、单skin/
单primitive布局，是本地验证脚本，**不是**通用GLB生产解析器。不能借此宣称
normalized weights、多sets、sparse、多个skin/mesh或压缩支持已经完成。
报告不是用原始神经weights替代实际导出数据；两个数据域计数不能混用。

## 工具接入的真实证据

`.local/runs/2026-10-09-skin-check-tool/`：真实CLI/MCP报告，以及execute
沙箱输出均为698962顶点、同侧混合671/527、suspicious、接受标记false。
源hash保持，没有重新生成/绑定/动作搜索。首次verifier的execute config使用
Python tuple导致JSON约定拒绝，原日志保留；continuation读既有CLI/MCP产物，
改从JSON配置加载数组后execute通过，并验证最终strict parser与报告一致。
这不是模型或生产工具失败，也没有重置旧task。没有新增Blender形变证据。

## 下一实现小步

1. 固定关节形变探针与近景输出：保存原标签/顶点集合比较，让极值与局部帧
   成为证据；原区域/2mm接触闸另跑，未过不得交付动画。
2. 明确语义种子与几何边界，再研究权重约束；不得靠减少统计数量当修复通过。

更可靠的语义分区与蒙皮约束仍在研究；此前UV颜色候选视觉不通过，不能用
调诊断阈值、少报样本或换区域标签掩盖残余尖刺。
