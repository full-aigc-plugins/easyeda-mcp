# 从内置 MCP 调用 .eext

先从服务实际工具列表确认前缀，本机为 LCEDA-Pro.help/discover/call。列出会话并选择实际 alive ID。安装后应先检查 functions 中存在 extension.json 的 UUID 且已启用，再查询扩展注入命名空间：

```json
{"path":"doc.external","input":{"session":"实际会话ID","className":"easyedaMcp"}}
```

查询 invoke 帮助，再调用：

```json
{"path":"invoke","input":{"session":"实际会话ID","code":"return await external.easyedaMcp.inspectProject({});","timeout":15000}}
```

接口注册在官方 sandbox 的 external Proxy 下，不是 eda.sys_ExternalApi.call。需指定权限上下文时，extUuid 使用 extension.json 中的真实 UUID；不要伪造内置扩展身份或通过切换身份绕过用户权限。是否需要外部交互许可由实际客户端决定。

本机 4.1.71 已实际安装并发现 14 个接口。主页的 `doc.external` 返回 BRIDGE_NOT_READY 时，使用已实测的只读帮助入口：

```json
{"path":"invoke","input":{"session":"实际会话ID","code":"return await eda.sys_Help.help(\"external\",\"easyedaMcp\");","timeout":10000}}
```

这不是切换 MCP 服务：调用仍经过客户端内置 MCP。扩展内部没有通用脚本执行工具。

原生包装可能包含 MCP isError、命令 ok/data，以及领域函数自身 ok，逐层检查。工程为空时返回 no_project；只有工程但无活动图页时返回 project_only；工程 API 挂起但活动图页提供父工程 UUID 时，只读响应附带 warnings 和 projectInfoSource=active_document；不要创建工程补测试。写入超时后按 ID 回读实际对象，不盲目重放。

修改示例仅在用户开启修改并授权任务后使用：

```javascript
await external.easyedaMcp.placeSchematicComponents({projectUuid:"实际工程UUID",documentUuid:"实际图页UUID",components:[{libraryUuid:"已查询的库UUID",deviceUuid:"已查询的器件UUID",x:100,y:100,designator:"U1"}]});
```

制造导出请求示例：

```javascript
await external.easyedaMcp.exportManufacturing({projectUuid:"实际工程UUID",documentUuid:"实际PCB UUID",formats:["gerber","bom","pickAndPlace"],delivery:"filesystem",outputDirectory:"/用户授权的输出目录"});
```

宿主需对输出文件再做 ZIP/层/钻孔、位号、坐标、格式与可预览性检查。byteVerified 只表示文件字节回读一致。
