# 蒙皮质量检查：只读内核

已提供 `skin-check` CLI、`figura_skin_check` MCP 和执行器同名步骤，共用engine。
GLB读取器与只读内核完成；另有`skin-probe`固定姿态形变、近景与诊断时间轴。
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

1. 用已保存的固定探针、冻结集合与近景评估语义分界与权重候选；不得靠减少
   统计数量当修复通过。
2. 原区域/2mm接触闸另跑，未过不得交付动画；诊断probe不是安全动作。

## skin-probe：形变与真实画面

```sh
openfigura skin-probe <task> --artifact model.glb --config probe-config.json
```

MCP为`figura_skin_probe(task_root, config, artifact)`，execute步骤为`skin-probe`，
params为`config, artifact`并声明model AssetRef。三入口共用engine。

```json
{"probes":[{"bone":"mixamorig:LeftHand","axis":"X","degrees":30,
             "track_groups":["mixamorig:LeftUpLeg","mixamorig:LeftLeg"]}],
 "resolution":768,"samples":8,"crop_extent_ratio":0.2}
```

需要静态rest骨架的嵌入GLB；已有动画、外部贴图/buffer、shape keys、多armature
或拓扑变更modifier拒绝。1–8个独立局部轴探针（X/Y/Z、非零±180°内），
跟踪组必须在模型中有正权重；每次恢复原矩阵，保持原标签和冻结的**正权重
分组并集**。这比按主导骨单标签的区域宽，不能把统计当真实解剖分区或与
旧主导标签数量直接比较。报告给出取景、掩码hash、分位数、峰值和极值样本。

顶点编号是**导入后的Blender mesh本地编号**，不是原GLB accessor编号。
新版报告带`vertex_index_domain`；本轮高模运行报告在该纯metadata增补前生成，
解释相同，后续严格validator已核对它仍有效。新字段在后续合成烟测实跑验证。
位移>0.002是GLB世界单位诊断，不是接触闸pass，不改变碰撞margin。

每次生成独立`diagnostics/skin-probe-<id>/`：机器报告、rest full PNG、每探针
full/closeup PNG、`skin-probe.blend`。closeup定位跟踪集合中最大位移顶点，
不能保证显示背面；全身PNG根据姿态重新取景。blend有rest及每个孤立探针
关键帧、CONSTANT插值，用于检查时间轴；saved camera使用rest边界，巨大
形变时应在Blender轨道视图检查，不能当所有播放帧都自动取景。

接受字段全false、visual pending。失败产物保留为未交付诊断；engine私有输入
快照/hash、输出文件验证及任务内目录约束，输出父目录symlink拒绝，防止越界。
缓存身份包括backend、worker、Blender binary与共享GLB reader。

真实高模两侧手腕30°在execute沙箱完成：7个产物，13.82s；root查看两张768
近景，左右裤面撕裂仍明显。跟踪并集392405点，各侧>0.002位移4703/4561，
这包括正常手部因微弱腿权重而被纳入的点，不能叫4703/4561个裤腿错误。
第一次加载worker时取景修复恰好并发落地，先前13.39s证据保留；冻结后新
hash阶段复验，未覆盖旧阶段。随后parent guard/report metadata/validator小修
用合成烟测验证，既有高模报告通过最终validator，无再次高模渲染。

独立重新打开真实blend，按[1,2,3,1,3,2]乱序播放：两次rest hash一致，姿态
样本最大误差1.49e-8世界单位。证明该诊断时间轴可重放，不证明碰撞安全或
人物可交付。批次`.local/runs/2026-10-09-skin-probe-tool/`，review-playback.json
保存实际argv/stdout/exit/hash；源rig保持，美术pending。

更可靠的语义分区与蒙皮约束仍在研究；此前UV颜色候选视觉不通过，不能用
调诊断阈值、少报样本或换区域标签掩盖残余尖刺。
