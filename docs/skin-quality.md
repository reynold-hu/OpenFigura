# 蒙皮质量检查：只读内核

当前范围为 `core.skin_quality.analyze_weights`，已实现内核；**不是完整
skin-check 工具**。CLI／MCP／执行器、通用GLB解码、固定姿态形变与近景报告
尚未接入，不替代接触闸或美术认可，也不自动修正权重。

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

## 下一实现小步

1. stdlib GLB权重读取器：明确支持范围，遍历实际skinned nodes/primitive；
   关节局部索引映射到正确skin，检查counts/stride/bounds、重复影响聚合。
   多sets和normalized支持必须测试，未支持的sparse/compressed明确拒绝。
2. engine先提供只读skin-check入口，私有输入快照、hash和报告声明；再镜像
   CLI／MCP／执行器，身份包含解析与检查模块，不把诊断完成等同质量pass。
3. 固定关节形变探针与近景输出：保存原标签/顶点集合比较，让极值与局部帧
   成为证据；原区域/2mm接触闸另跑，未过不得交付动画。

更可靠的语义分区与蒙皮约束仍在研究；此前UV颜色候选视觉不通过，不能用
调诊断阈值、少报样本或换区域标签掩盖残余尖刺。
