# EDA 内部扩展协作规则

- 当前主目标为可安装 .eext；src/ 是浏览器沙箱扩展，不能使用 Node/DOM；iframe/ 可使用 DOM；build/config 为开发工具。
- 外部接口统一注册在 easyedaMcp，通过官方 sys_ExternalApi 暴露；不再创建独立 MCP/WebSocket 服务。
- 结构以项目内 pro-api-types 类型声明和官方 eda-api.js 查询结果为准。
- 新接口同时更新 operations.ts、测试和 README。默认只读，不自动打开、切换、创建工程或保存。
- 用户开启修改后只执行明确请求；失败/超时先回读，保留部分变更信息。
- npm test；npm run build；python3 scripts/check_eext.py。
- 安装到 EDA 前遵守用户的插件安装确认规则；不把隔离测试称为真实客户端验收。
