# 本地产物治理

唯一产物根：主仓库 `OpenFigura/.local/`，不进Git。开发worktree复用同一位置。

- `runs/<批次>/`：输入副本、阶段任务、GLB/Blend、贴图、render、日志和诊断。
- `catalog.json`：批次索引、旧路径→新路径、清单及迁移验证状态。
- `manifests/<批次>.json`：文件相对路径/大小/SHA256，便于迁移后核验和定位。

新批次用日期加目的命名，例如`2026-10-09-xiaoman-contact`；同一批次任务依旧
按Task ID和stage ID区分。pass/fail、技术/视觉状态分别记录，不按文件存在判成功。
失败候选保留在批次内，不混到delivery。Golden源图/候选和用户未提交文件不搬。
权重与外部runtime继续留`Local/Opensource`，不归入产物。

2026-10-09迁移桌面10个`openfigura-*`测试目录；保留原批次名。完整证据文件
不改写，迁移前后逐文件hash核验。过去PROGRESS与账本中的桌面路径是历史事实，
按catalog对应的新根加相对路径读取。重放旧脚本前显式重定位路径，不能假设旧
绝对路径仍存在；不要为方便把桌面目录再创建出来。

恢复迁移：先确认catalog中对应原位置不存在及无任务运行，然后把整个批次目录
移回catalog.source，核对manifest。默认没有永久删除；清理生成失败物另行记录。

最新审查入口：`.local/runs/openfigura-review-2026-10-09/`，scifi对照为其
`scifi-uv-trial/compare.html`。新小满低模渲染有严重黑斑，动作也被接触闸拒绝，
属于诊断失败候选，不是可交付人物。
