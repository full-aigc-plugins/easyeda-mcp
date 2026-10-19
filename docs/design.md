# 原生 MCP 领域适配设计

用户要求在技能包和插件完成后提供更强的 easyeda-mcp。本版按高级 MCP 封装理解，独立目录 easyeda-mcp；不是 EDA 内部 .eext。未安装任何软件，不初始化规格体系或 Git，不更改全局 MCP 配置。

既有能力是官方 help/discover/call 与动态 doc.api/invoke；缺口是面向任务的参数、目标识别、结果裁剪与文件字节校验。复用原生执行器，新增本地 stdio 入口。当前环境未安装 Python MCP SDK/Pydantic，采用标准库实现限定的工具服务，不静默安装依赖。协议以 2025-06-18 stdio/Tools 规范为依据；不提供远程 HTTP Server、通用 SDK 替代或独立 WebSocket Bridge。

11 个工具由 server.py 显式定义并验证入参，workflows.py 组织原生调用。连接默认 15 秒，长耗时 invoke 按具体工具设置执行与 HTTP 上限，调用后恢复；无自动写入重试。以实时 API 目录验证方法和 mount，不使用文档示例作为可执行代码。

工程读写调用在 invoke 内再次核对焦点文档和工程 UUID，收窄 UI 焦点漂移窗口；客户端 API 依赖当前文档，执行过程中用户切换焦点仍需避免，不宣称具备编辑器事务锁。不会自动保存或创建工程副本。

工程写入需要 --allow-write；导出需要单独配置 --output-root，使用新文件、受限路径、字节数/SHA256 与 ZIP 检查。已生成的部分文件在失败时明确报告，不伪装原子回滚。20MiB 单文件上限是本版边界。

验收包含离线协议/工作流测试、真实 stdio→官方 MCP 只读链路、Codex 本地插件发现。真实工程写入、DRC、布线和导出没有执行；不把工具存在当成全流程成功。
