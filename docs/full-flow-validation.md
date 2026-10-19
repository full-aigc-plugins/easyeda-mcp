# EasyEDA 独立 LED 工程全流程验收

日期：2026-10-19。客户端：嘉立创 EDA 专业版 4.1.71.7a7261be，macOS。
Codex Agent 插件：EasyEDA 0.1.0-dev.20261019.4，33 个技能，官方 CLI 安装并读回 installed=true、enabled=true。
EDA 内部扩展：EasyEDA MCP 0.1.0-dev.20261019.3，14 个领域接口。继续使用官方内置 MCP，不使用独立 stdio 试作或 Gateway。

## 实际结果

| 阶段 | 结果 |
|---|---|
| 从零新建 | 新工程“EasyEDA AI 全流程独立测试 20261019”，不是编辑原工程或清空示例 |
| 原理图设计 | J1 两针输入、R1 1kΩ、D1 红色 LED；真实库器件，3 个器件、6 个引脚 |
| 连接核对 | VCC=J1.1/R1.1，LED_A=R1.2/D1.1(A)，GND=J1.2/D1.2(K)；实际网表完全一致 |
| 原理图 DRC | 严格检查 0 违规 |
| 同步 PCB | 同 Board 的 Schematic1→PCB1，导入确认窗应用后回读 3 个器件及相同 pad/net |
| 板框 | 闭合折线，25.4×20.32mm；普通 Line 在本客户端板框层创建失败，改用公开 Polyline API 成功 |
| 自动布局 | 3/3 完成，无失败器件；位置回读均在板框内 |
| 自动布线 | 3/3 网络完成，failedNets=[]；实际回读 6 段顶层铜线，约 10mil |
| PCB DRC | 严格检查 0 违规 |
| 保存并重开 | 原理图、PCB 保存返回成功；复制新建测试工程完整目录到工作区后，在新窗口从磁盘打开 |
| 重开后数据 | 3 个 PCB 器件、6 段走线；原理图 6 个连接一致；两种 DRC 仍均 0 违规；默认只读 |
| Gerber | 15,079 字节 ZIP，13 项，CRC 通过；含上下铜、上下阻焊、丝印、锡膏、板框及镀通孔钻孔等 |
| 钻孔 | 实际 Excellon 2 孔，孔径 1.10002mm，与两针连接器对应 |
| BOM | 688 字节，3 行、总数量 3、位号 D1/J1/R1、真实供应商料号 |
| 贴片坐标 | 1,580 字节，3 行；mm 坐标与 PCB mil 坐标换算误差小于 0.001mm；J1 标记非 SMD |
| 工程归档 | 原生 .epro2 29,476 字节，ZIP CRC 通过；另交付完整 .eprj3 文件夹及依赖文档 |
| 预览 | 客户端真实原理图/PCB 已检查；原理图原生 SVG/PNG；Gerber 顶铜+丝印+板框+钻孔按实际文件解析生成 SVG/PNG 并查看 |

## 调用与权限的实测要求

- 省略 extUuid 的 invoke 使用独立脚本上下文。调用 external.easyedaMcp 时，需从 functions 核对真实扩展 UUID；本机为 b0f54bac131848dab885c8215a0ac81c。绑定该 UUID 后可看到经客户端确认的 writeEnabled=true。没有使用内置 eda 身份冒充或参数打开权限。
- 修改模式仅在测试会话的面板确认；完成后恢复只读。用户原会话始终未调用工程写入，最后读回仍为主页 no_project、writeEnabled=false。
- importChanges 返回 true 只打开确认窗口，不能当作导入完成。实际应用后才回读器件与网络。
- openDocument 在部分后台/冷启动窗口超时，但图页可能已经打开。先回读活动文档；没有把超时请求当作未执行而重复工程写入。
- 原测试工程 UUID 为 fe24efeb9f5fd45fcd77b6157b0c7f7931ddbd2eb521200873a470bfb2b1a0d9。目录复制到交付路径后 UUID 变为 d5ad5a0061d4af3ad25c1dd23542bc098ad0788f538b4f9d6c3786fea3786bb2，文档 UUID 保持。重新发现身份后验证，未沿用旧工程 UUID。
- BOM/坐标文件虽扩展名为 .csv，原始字节实际是 UTF-16LE BOM、TAB 分隔。保留原文件，另附 UTF-8 BOM/逗号版本；坐标原始单位有 mm 后缀。
- 工程创建、同 Board 同步和板框采用官方 eda API 补足，权限确认/导入确认使用真实客户端 UI；14 个领域接口本身尚未封装这些步骤。因此这是经过内置 MCP 与客户端 UI 跑通的单一低压电路验收，不声称任意项目均可无人值守全自动完成。

## 交付与复验

上述设计基线、网表、工程、制造文件、预览和机器回执位于本机 easyeda-mcp/artifacts/led-e2e-20261019；该目录按源码仓库提交规则忽略。本报告作为验证摘要保留，clone 仓库不会包含这些本机验收产物。
在 easyeda-mcp 根目录运行：

```bash
python3 -B scripts/verify_led_e2e.py artifacts/led-e2e-20261019
```

verification.json 为实际文件检查结果；manufacturing-validation.json 包含坐标对照；reopen-validation.json 为新窗口读取结果；session-scope-validation.json 说明测试窗口清理及原窗口状态。Gerber 预览器仅接受本次输出的 G01、C/R 光圈子集，遇到未知弧线/区域拒绝解析，不是通用 CAM/DFM 引擎。

未执行生产下单、付款、实物打样、焊接、电气测量或制造商在线 DFM。库里的 Vf 参数与计算只作为低压测试基线，不替代实物验证。本验收发生于源码首次提交前；Git 托管状态以仓库当前提交为准，未创建产品 Release。未修改用户原工程，保留原用户窗口；工具创建的后台窗口已关闭，另保留默认只读的交付工程窗口供查看。
