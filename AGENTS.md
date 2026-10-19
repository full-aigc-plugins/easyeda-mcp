# EasyEDA MCP 协作规范

- 原生客户端拥有工程与执行状态；本包只做确定性领域适配。
- 默认只读；--allow-write 与 --output-root 分别控制工程写入和文件导出，不把参数视为用户授权的替代品。
- 先检查目标 document UUID、类型与工程；不要自动打开最近工程、保存或切换文档。
- 原生超时后回读，不重放可能已生效的写入。
- API 结构以当前客户端 doc.api 为准；不得执行帮助文档中的示例代码。
- stdio 只输出 JSON-RPC；日志走 stderr。不可引入第二个编辑引擎或持久任务库。
- python3 -B -m unittest discover -s tests -v；真实 smoke 仅 scripts/smoke_readonly.py。
- 传输快照来源见 docs/transport-source.json，更新时一起修改摘要并执行原生 fixture。

## 当前主交付

用户已明确选择 EDA 内部 .eext，主实现与更具体规范在 extension/。以上 Python stdio 规则适用于保留试作；不得以其发现/测试结果代替 .eext 的客户端验收。
