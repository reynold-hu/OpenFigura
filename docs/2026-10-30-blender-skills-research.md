# Blender Skills 与 OpenFigura 对照调研

日期：2026-10-30。上游仓库：
[arjun988/blender-skills](https://github.com/arjun988/blender-skills)，固定提交
`8f778d2405a214b508d4c7d80742be8e43acdd52`，MIT License。

## 它到底是什么

Blender Skills 是 94 个 Agent skill 文件和 175+ 个参考文档，覆盖建模、UV、
材质、灯光、绑定、动画、优化、碰撞、Godot/Unity/Unreal 导出和 QA。它通过
`blender-director` 做路由，把一个创作请求拆成多个技能。真正执行需要另装
BlenderMCP addon；README 的 Codex 方式是把 `.claude/skills` 复制或链接到
Codex skills 路径，再通过 MCP 控制 Blender。

它没有替代 Blender 的几何、蒙皮或动作模型，也没有自动提供无碰撞保证。Skill
文件里的“AAA”“game-ready”等描述是流程指导，必须由真实 Blender 产物和引擎
检查证明。它的 README 没有把 94 个技能的成功率当成测试结果。

## 与 OpenFigura 的关系

| Blender Skills | OpenFigura 现有能力 | 结论 |
|---|---|---|
| blender-director 路由 | `skills/openfigura/SKILL.md` + CLI/MCP engine | 吸收请求分类和阶段路由，保留 OpenFigura engine 为唯一执行源 |
| reference-image-match | preflight、render、golden cases、真实帧 | 吸收“先镜头/比例，再细节”和固定截图对比 |
| asset-optimization | mesh inspect/optimize/retopo/UV、skin-check | 吸收预算/命名/UV/材质报告，但不把其规则当自动通过 |
| qa-review | render、evaluate、visual_approval | 吸收明确的 SHIP/NO-SHIP 结构，保留人工审美闸 |
| collision-proxy | collision mesh 工具、motion gate | 可补充引擎碰撞命名和代理资产检查，但不能替代现有接触闸 |
| godot-export/export-pipeline | export presets、GLB/FBX/USD、Godot 证据 | 适合作为导出清单的参考；实际轴向、哈希和引擎导入仍以 ledger 为准 |
| Blender MCP | OpenFigura MCP server | 不直接接管 OpenFigura；Blender MCP 可以成为可选外部执行器，结果必须回到任务/ledger |

## 可以直接迁入 OpenFigura 的改进

1. 在 `skills/openfigura/SKILL.md` 增加导演式路由：输入分析 → 生产 brief →
   生成/建模 → 材质/UV → rig/skin → motion gate → export → QA。
2. 为每个阶段声明“输入、输出、失败条件、真实画面证据”，让 Agent 不会把
   Blender 操作描述误当成已完成。
3. 在导出前固定一份 QA 检查：三/四分之三、侧面、材质、线框/拓扑、动画帧、
   engine import；所有结果写入 `.local/runs/<batch>/`。
4. 将 Blender Skills 的 specialist 名称映射成 OpenFigura 的 engine verbs，
   但不复制其 MCP 配置或自带 Blender 插件：

   `character-artist → generate/autorig/skin-check/skin-probe`

   `uv-workflow → mesh uv/bake/refine-texture`

   `asset-optimization → inspect/mesh/print-check/score`

   `rigging/animation → rig/transfer-rig/animate/retarget/motion-gate`

   `collision-proxy → mesh collision + contact gate`

   `godot-export → export --format glb + Godot evidence`

5. 增加候选对比和明确的 `NO-SHIP` 结果。OpenFigura 已有 candidate batches、
   render 和 human review 字段；下一步可以把这些关系写成一个更小的导演 skill，
   而不是引入完整 94 技能目录。

## 不应该直接复制的部分

- `.claude/skills` 全量复制会增加上下文、产生重复工具说明，并且会把 BlenderMCP
  的外部状态误认为 OpenFigura 的可审计执行结果。
- 它的 MCP 配置面向外部 BlenderMCP addon；OpenFigura 的 `figura_*` 契约、输入
  hash、缓存和失败隔离必须继续由 engine 控制。
- 其预算、命名和“game-ready”规则是通用建议，不适用于所有 Q 版角色和我们
  现有半写实资产，必须转为参数化检查。
- 任何 Blender Skills 依赖的模型、addon、外部脚本、权重都不能因为 Skill 文件
  被复制就自动获得许可证或商用权。

## 最小迁移结果

本轮只研究上游，没有复制其源码或 BlenderMCP addon。OpenFigura 的 Skill 文件已
补充阶段路由与证据闸；上游完整克隆留在
`~/Desktop/Local/Opensource/blender-skills`，便于后续逐个技能审阅。下一步若要
实现，优先做一个 1 个入口的 OpenFigura director skill 和一个候选 QA/对比报告，
然后用当前 `skin-probe` 与 `motion-gate` 真实验证，不先引入 94 个目录。
