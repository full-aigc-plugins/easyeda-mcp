# EasyEDA MCP

当前主交付为 **嘉立创 EDA 内部 .eext 扩展**，源码和安装包位于 [extension/](extension/README.md)。14 个领域接口通过客户端内置 MCP 与 `external.easyedaMcp.*` 使用，带 EDA 内部面板，默认只读。

已按用户授权安装 `.eext` 版本 `0.1.0-dev.20261019.3`，完成 14 个接口发现及原理图/PCB、引脚、网表只读检查；详见 [本机验证](docs/client-validation.md)。构建：在 extension 中执行 `npm ci --ignore-scripts`、`npm test`、`npm run build`。

已完成独立 LED 测试的原理图设计、PCB 同步、自动布局布线、严格 DRC、保存重开和制造文件导出；详见 [全流程实测](docs/full-flow-validation.md)。输出保留在本地 artifacts/led-e2e-20261019，该目录已忽略，不随源码仓库提交。

以下保留前序 stdio 试作的说明，其工具发现结果不代表内部 .eext 的安装或验收。

---

# EasyEDA MCP

在嘉立创 EDA / EasyEDA 专业版**内置 MCP**之上提供 11 个领域工具，版本 `0.1.0-dev.20261019.1`。原生客户端继续负责电路编辑、布局布线与制造文件生成。本包提供工程识别、参数适配、分页、错误判断与实际文件校验。

本地开发候选，未发布/安装到全局。默认只读；已有官方原生服务为 `http://127.0.0.1:31637/mcp`。不需要 Run API Gateway，也不启动第二个编辑器或桥接服务。

## 启动与配置

仅依赖 Python 3.10+ 标准库，无需 pip install：

```bash
python3 -B scripts/serve.py
```

这是 MCP stdio 服务，会等待宿主输入 JSON-RPC；stdout 不能用于普通日志。可从任何 cwd 用 serve.py 的绝对路径启动。宿主配置样例见 [examples/codex-mcp.toml](examples/codex-mcp.toml) 和 [examples/mcp.json](examples/mcp.json)，修改为实际绝对路径后再加载。本次没有执行全局安装或改写全局配置。

首次任务：“只读检查当前工程，先执行 easyeda_doctor，再 easyeda_inspect_project”。多会话传入实际 session。工程为空返回 no_project，工具不会打开最近工程。

## 工具

| 工具 | 能力 |
|---|---|
| `easyeda_doctor` | 连接、版本、桥接与结果通道 |
| `easyeda_list_sessions` | 会话与实际 sessionId |
| `easyeda_inspect_project` | 工程、活动文档、板子、原理图页、PCB |
| `easyeda_get_api` | 当前客户端的 API 签名 |
| `easyeda_list_components` | 器件 ID/位号/坐标分页 |
| `easyeda_read_netlist` | 原理图网表文本分页 |
| `easyeda_check_drc` | 当前图页的严格 DRC 布尔结果 |
| `easyeda_call_api` | 经实时 mount/方法校验的领域 API 调用，需写入模式 |
| `easyeda_auto_layout` | 官方 PCB 自动布局，需写入模式 |
| `easyeda_auto_route` | 官方 PCB 自动布线，保留失败网络，需写入模式 |
| `easyeda_export_manufacturing` | Gerber/BOM/贴片坐标，需输出根目录 |

## 写入、布线和导出

用户授权修改后，宿主可用 `--allow-write` 启动。`easyeda_call_api` 提供 DMT/SCH/PCB/LIB 的通用 JSON 参数入口，不能注入 JavaScript 或调用 SYS 文件/网络接口。先查 API 签名、枚举与单位；修改后的图元和复杂返回需要专门回读，不能把 returned 当成验证成功。通用工具不支持把跨次调用的原语对象当作参数。

每次操作要求明确 document_uuid，先匹配当前文档和类型，再在同次 invoke 内核对焦点。用户在调用执行期间应保持目标图页；这不构成编辑器级事务锁。不会自动保存、删除既有布线或下单付款。自动布局/布线耗时较长，需宿主允许相应超时；超时后先读结果，不自动重放。

文件导出单独配置 `--output-root /授权输出目录`，不要求开启工程修改模式。工具仅写入此根目录中的新文件，已有文件不覆盖。Gerber 使用当前客户端的一键默认层/对象，BOM 和贴片坐标使用 CSV，贴片坐标为 mm。实际字节数/SHA256 与 Gerber ZIP CRC 会检查；板框、铜层、钻孔、电气与坐标正确性仍须回读和预览。单文件上限 20MiB，失败时报告已生成文件。

## 验证

```bash
python3 -B scripts/validate_package.py
python3 -B -m unittest discover -s tests -v
python3 -B scripts/smoke_readonly.py
```

离线测试覆盖只读模式、文档 UUID/焦点变化、错误 DRC 结果、失败网络保留、输出目录逃逸、禁止覆盖、实际字节与 stdio 协议。`smoke_readonly.py` 启动真实 MCP 子进程，调用 doctor、会话、工程和 API 帮助，并验证写入模式关闭。它不导出或修改工程。脚本使用 POSIX pipe/select，已在本机 macOS 执行；服务本身没有此平台依赖。

最近实测服务为 JLCEDA Pro 4.1.71.7a7261be，doctor connected=true/versionMatch=true/resultChannel=true；工程仍返回 null，因此工程内容、DRC、自动布局/布线和制造导出**未做真实板卡验收**。该早期只读回执仅保留在本地，不随源码提交；当前 .eext 的完整验收见前文全流程实测。协议测试通过不代表模型已经在宿主内完成任务。

本地传输实现限定于已实测官方 JSON 响应，不是全功能 MCP SDK；不提供 SSE 消息流、跨请求后台任务或取消/恢复。长调用返回前不能处理其他工具请求。后续需要这些能力时优先使用官方 SDK，不扩展成另一套 Agent Runtime。

协议依据：[MCP stdio](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)、[MCP tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)。来源与设计见 docs/design.md、docs/transport-source.json、NOTICE。

Codex app-server 在临时 -c 配置下已发现全部 11 个工具，toolsError=null；该机器回执仅保留在本地，不随源码提交。这是宿主工具发现验证，未创建新聊天或运行模型任务。

本地 ZIP：`python3 -B scripts/build_package.py`，产物位于 dist，包含独立运行所需代码与文档。

源码仓库：[full-aigc-plugins/easyeda-mcp](https://github.com/full-aigc-plugins/easyeda-mcp)。Git 仅保留源码、锁文件、自动化测试、CI 与说明文档，不提交 node_modules、构建输出或临时测试工程；当前尚未创建正式 Release。
