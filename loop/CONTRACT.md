# Loop 工作约定

- STATE.md 保存最新事实和接续点，TASKS.md 保存验收勾选，PROGRESS记录已验证证据。
- “pass”需要命令退出码、输出文件和检查报告；visual_approval 由用户决定。
- 运行日志、参考输入、GLB/Blend、贴图和渲染存桌面证据目录，权重和运行时不入库。
- 失败候选保留、隔离；不复用旧 .blend 冒充新生成，不用代理凸包证明动画不穿插。
- 没有明确报告的硬件、API或服务能力不能默认可用；重任务不能因前端超时重复启动。
- 验收矩阵中的每项标记 implemented/tested/visually-reviewed，三者不互相代替。
- 单测、MCP/CLI与真实程序调用分别验证，跨平台未运行则记未验证。
- 修改采用小提交、DCO，保持用户未提交内容；不force-push。
