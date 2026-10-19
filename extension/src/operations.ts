/** 同一目录用于 External API 帮助、面板与可发布接口文档。 */
export const operations = [
    { name: 'getCapabilities', title: '能力与只读状态', write: false, fields: '无必填字段' },
    { name: 'inspectProject', title: '读取当前工程与原理图/PCB', write: false, fields: '无必填字段' },
    { name: 'searchDevices', title: '按关键词查询真实器件库', write: false, fields: 'query:string；可选 page、limit' },
    { name: 'listComponents', title: '分页读取当前图页器件', write: false, fields: 'projectUuid,documentUuid；可选 offset,limit(1~200)' },
    { name: 'getPins', title: '读取器件真实引脚与端点', write: false, fields: 'projectUuid,documentUuid,primitiveId；原理图' },
    { name: 'getNetlist', title: '分页读取原理图网表', write: false, fields: 'projectUuid,documentUuid；可选 offset,limit(1~100000)' },
    { name: 'checkDrc', title: '严格 DRC 与违规明细', write: false, fields: 'projectUuid,documentUuid；原理图或 PCB' },
    { name: 'placeSchematicComponents', title: '批量放置原理图器件', write: true, fields: 'projectUuid,documentUuid,components:[{libraryUuid,deviceUuid,x,y,rotation?,designator?}]；坐标 10mil' },
    { name: 'connectPins', title: '按引脚编号连接原理图网络', write: true, fields: 'projectUuid,documentUuid,from:{primitiveId,pinNumber},to:{primitiveId,pinNumber},netName；可选 waypoints:[{x,y}]；坐标 10mil' },
    { name: 'placePcbComponents', title: '批量放置 PCB 器件', write: true, fields: 'projectUuid,documentUuid,components:[{libraryUuid,deviceUuid,x,y,layer?(1/2),rotation?,designator?}]；坐标 mil' },
    { name: 'autoLayout', title: 'PCB 自动布局', write: true, fields: 'projectUuid,documentUuid；Beta，完成后回读器件位置和 DRC' },
    { name: 'autoRoute', title: 'PCB 自动布线', write: true, fields: 'projectUuid,documentUuid；可选 nets:string[]；Beta，检查 failedNets 和 DRC' },
    { name: 'saveDocument', title: '显式保存当前文档', write: true, fields: 'projectUuid,documentUuid；不会随其他操作自动保存' },
    { name: 'exportManufacturing', title: '导出 Gerber / BOM / 贴片坐标', write: false, fields: 'projectUuid,documentUuid,formats:[gerber|bom|pickAndPlace]；delivery:base64(默认)|dialog|filesystem；filesystem 必须指定 outputDirectory；可选 prefix。会生成文件，不是工程内容修改。' },
] as const;
export const NAMESPACE = 'easyedaMcp';
export const RPC_TOPIC = 'easyeda-mcp:request';
