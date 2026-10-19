# 本机客户端验证

目标：嘉立创 EDA 专业版 4.1.71.7a7261be，macOS，2026-10-19。

通过扩展管理器导入 .eext。默认只读，未开启工程修改，未开启外部交互权限。14 个接口通过 sys_Help.help("external","easyedaMcp") 可发现；doc.external 在当前主页 render 返回 BRIDGE_NOT_READY，直接 invoke 外部命名空间可调用。面板在真实客户端加载。

用户当前窗口为主页，inspectProject 返回 no_project。额外验证采用访达复制的官方“示例工程_快速入门”和“示例工程_面板打印设计”副本，只在工作目录内打开。终端对 Documents 原文件受 TCC 限制，未声称对原文件进行哈希校验；未打开或保存原文件。

发现快速入门副本的 getCurrentProjectInfo 会挂起，而原理图页、PCB 目录和器件 API 正常；扩展增加 1500ms 只读降级，使用活动图页返回的真实 parentProjectUuid 并保留 warning。修改/保存仍拒绝不完整身份。详细复验结果在安装更新后补入。

未验证：真实工程创建、连线、自动布局布线、保存、DRC/制造文件导出；不会以本地模拟测试替代板卡与制造验收。没有提交、推送或发布。
