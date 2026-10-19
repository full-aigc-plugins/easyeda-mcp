# EasyEDA MCP — 嘉立创 EDA 内部扩展

本目录交付安装到嘉立创 EDA **专业版**中的 `.eext`。版本 `0.1.0-dev.20261019.3`，显示名 **EasyEDA MCP**。通过官方内置 MCP 使用 `external.easyedaMcp.*` 领域接口；不启动独立 MCP 服务或 WebSocket Bridge。

## 使用

1. 在客户端扩展管理器导入 `build/dist/easyeda-mcp_v0.1.0-dev.20261019.3.eext`，启用扩展。安装属于独立授权步骤。
2. 从顶部 **EasyEDA MCP → 打开面板** 读取当前工程。激活只注册接口，不创建、打开或保存工程。
3. Codex 继续连接客户端内置 MCP。通过 `doc.external` 查询 `easyedaMcp` 帮助；若返回 BRIDGE_NOT_READY，通过 `invoke` 调用 `eda.sys_Help.help("external","easyedaMcp")`，再使用 `invoke` 调用 `external.easyedaMcp.inspectProject({})`。调用示例见 [原生 MCP](docs/native-mcp.md)。
4. 已授权修改时，通过菜单/面板 **开启工程修改**；在客户端确认后，本次扩展会话才允许创建器件、连线、布局/布线与显式保存。重载后恢复默认只读。

## 接口

| 接口 | 功能 |
|---|---|
| getCapabilities | 只读状态、单位及版本能力 |
| inspectProject | 工程、活动文档、板子、原理图页、PCB |
| searchDevices | 按关键词查询真实器件库，支持分页 |
| listComponents | 器件 ID、位号、位置与旋转，支持分页 |
| getPins | 原理图器件引脚编号、名称和真实端点 |
| getNetlist | 原理图网表文本分页 |
| checkDrc | 严格 DRC 与违规明细 |
| placeSchematicComponents | 整批输入预检后放置原理图器件 |
| connectPins | 根据器件 ID/引脚编号连接命名网络，可指定 waypoints |
| placePcbComponents | 在顶/底层放置 PCB 器件 |
| autoLayout / autoRoute | 官方 PCB 自动布局、布线，保留原始结果与失败网络 |
| saveDocument | 显式保存指定活动文档 |
| exportManufacturing | Gerber ZIP、BOM CSV、贴片坐标 CSV |

接口返回 `{ok,data}` 或 `{ok:false,error:{code,message,partial?}}`，不能只检查传输成功。修改接口需要 projectUuid 和 documentUuid，取自 inspectProject 的真实结果。所有坐标：原理图 10mil、PCB mil。不会通过名称猜测器件库 UUID 或引脚。

连线默认使用简单正交路径，需要网表和 DRC 验证；没有自动避障保证。原理图创建不自动导入 PCB，PCB 器件/网络对应关系仍需使用原生 API 和技能按目标工程处理。不会把自动布线启动或 API 返回当成全部网络布通。

## 制造文件

exportManufacturing 的 formats 支持 `gerber`、`bom`、`pickAndPlace`；delivery 支持：

- `base64`：默认返回真实文件字节、名称和大小，供宿主保存；不写客户端磁盘。
- `dialog`：调用客户端保存窗口，只报告 download_requested；不推断用户是否完成保存。
- `filesystem`：明确指定绝对 outputDirectory，经客户端 API 写入，force=false，文件存在不覆盖；写入后回读并逐字节比对。仅桌面客户端有效，需在扩展管理器开启外部交互权限。

单文件上限 10MiB。Gerber 使用当前客户端默认层/对象；文件字节一致仍不能代替铜层、钻孔、板框、BOM/坐标一致性与制造预览。不自动下单或付款。

## 开发与检查

Node.js 24+，依赖仅安装在本目录。

```bash
npm ci --ignore-scripts --no-audit --no-fund
npm test
npm run build
python3 scripts/check_eext.py
```

固定官方 SDK 1.6.29，pro-api-types 0.4.26，TypeScript 5.9.3。类型声明摘要与已查询接口见 docs/sdk-source.json、docs/verified-api.json。部分活动文档、文件系统与自动布局布线 API 为 Beta，需目标客户端验证。

本地通过类型检查、领域与真实浏览器 bundle 的隔离测试，以及 .eext 结构检查。已在本机嘉立创 EDA 专业版 4.1.71 中安装并加载面板，通过内置 MCP 发现 14 个接口并读取只读状态和当前工程。当前用户会话位于主页，没有活动工程。另使用官方示例副本进行原理图/PCB 只读验证，详见 docs/client-validation.md。不会将这些检查混称为已完成真实电路设计或制造导出。

许可见 LICENSE / NOTICE；官方构建工具修订见 docs/sdk-source.json。

当 getCurrentProjectInfo 挂起时，1500ms 后只读读取可采用活动文档返回的 parentProjectUuid，结果标明 projectInfoSource=active_document 与 warnings，名称不猜测。修改/保存仍要求完整工程信息；超时不会重试原始 SDK 调用。
