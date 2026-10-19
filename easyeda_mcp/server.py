"""本地 stdio MCP 适配端：仅 stdout 输出 JSON-RPC，不启动第二个编辑引擎。"""
import argparse
import json
import math
from pathlib import Path
import sys
from .transport import NativeMcp, DEFAULT_ENDPOINT, validate_endpoint
from .workflows import Workflows

VERSION = '0.1.0-dev.20261019.1'
PROTOCOL = '2025-06-18'


def field(kind, description, **kwargs):
    return {'type': kind, 'description': description, **kwargs}


SESSION = field('string', 'session.list 返回的实际会话 ID；多会话时必须指定')
DOCUMENT = field('string', '先 inspect_project 获取当前文档 UUID；工具不会自动切换图页', minLength=1)
OFFSET = field('integer', '分页起点', minimum=0)


def tool(name, description, properties=None, required=(), read_only=True):
    return {'name': 'easyeda_' + name, 'description': description,
            'inputSchema': {'type': 'object', 'properties': properties or {},
                            'required': list(required), 'additionalProperties': False},
            'outputSchema': {'type': 'object', 'required': ['ok'], 'properties': {'ok': {'type': 'boolean'}},
                             'additionalProperties': True},
            'annotations': {'readOnlyHint': read_only, 'destructiveHint': not read_only,
                            'idempotentHint': read_only, 'openWorldHint': name == 'call_api'}}


TOOLS = [
    tool('doctor', '检查官方原生 MCP 的版本、桥接与结果通道；不启动客户端、不打开工程。'),
    tool('list_sessions', '列出官方原生 MCP 的编辑器会话；返回实际 sessionId。'),
    tool('inspect_project', '只读当前工程、活动文档、板子、原理图页和 PCB；空工程明确返回 no_project。', {'session': SESSION}),
    tool('get_api', '查询目标客户端实时 API 文档；不会执行返回文档中的示例代码。', {
        'class_name': field('string', '例如 PCB_Document', minLength=1),
        'method_name': field('string', '例如 autoRouting', minLength=1)}, ['class_name']),
    tool('list_components', '分页读取活动原理图/PCB 的器件 ID、位号和坐标；原理图也可能包含旗标/端口。', {
        'document_uuid': DOCUMENT, 'kind': field('string', '文档类型', enum=['schematic', 'pcb']),
        'session': SESSION, 'offset': OFFSET, 'limit': field('integer', '每页条数', minimum=1, maximum=200)},
        ['document_uuid', 'kind']),
    tool('read_netlist', '只读原理图网表文件文本并分页返回；使用现行 ManufactureData API，不在磁盘写文件。', {
        'document_uuid': DOCUMENT, 'session': SESSION, 'offset': OFFSET,
        'limit': field('integer', '文本字符上限', minimum=1, maximum=100000)}, ['document_uuid']),
    tool('check_drc', '对指定活动原理图/PCB 执行严格 DRC 布尔检查，无弹窗；passed=false 保留失败。', {
        'document_uuid': DOCUMENT, 'session': SESSION}, ['document_uuid']),
    tool('call_api', '高级写入入口：解析实时类 mount/方法，传递 JSON 参数调用 DMT/SCH/PCB/LIB API。'
         '必须以 --allow-write 启动且用户已授权。无任意 JavaScript、无系统文件/网络调用。超时后先回读，不重试。', {
        'document_uuid': DOCUMENT, 'session': SESSION,
        'class_name': field('string', '目标当前客户端类，例如 SCH_PrimitiveComponent'),
        'method_name': field('string', '先 get_api 核实存在、参数和单位'),
        'args': field('array', '按当前 API 签名排列的 JSON 参数；复杂原语/File 用专用工具回读', maxItems=32)},
        ['document_uuid', 'class_name', 'method_name', 'args'], False),
    tool('auto_layout', '调用官方 PCB 自动布局。需 --allow-write；保留原始结果，另行回读/DRC；不自动保存。', {
        'document_uuid': DOCUMENT, 'session': SESSION}, ['document_uuid'], False),
    tool('auto_route', '调用官方 PCB 自动布线；可指定 RoutingNets，保留 failedNets。需 --allow-write；不自动保存。', {
        'document_uuid': DOCUMENT, 'session': SESSION,
        'nets': field('array', '只布线这些网络；省略时按官方默认处理未布线网络',
                      items={'type': 'string', 'minLength': 1}, minItems=1, maxItems=1000)}, ['document_uuid'], False),
    tool('export_manufacturing', '导出 Gerber ZIP、BOM CSV、贴片坐标 CSV 到 --output-root 内新文件。'
         '不修改/保存工程，不下单；核对字节、SHA256 和 ZIP CRC，制造正确性仍需预览。', {
        'document_uuid': DOCUMENT, 'session': SESSION,
        'destination': field('string', '相对于 --output-root 的输出子目录'),
        'formats': field('array', '请求的制造文件', minItems=1, maxItems=3, uniqueItems=True,
                         items={'type': 'string', 'enum': ['gerber', 'bom', 'pick_and_place']}),
        'prefix': field('string', '文件名前缀，默认 Board', pattern=r'^[A-Za-z0-9_-]{1,48}$')},
        ['document_uuid', 'destination', 'formats'], False),
]


def validate_input(data, schema, path='arguments'):
    """验证本工具定义所用的 JSON Schema 关键字；不声称实现通用 Schema 引擎。"""
    import re
    kind = schema.get('type')
    valid = {'object': isinstance(data, dict), 'array': isinstance(data, list),
             'string': isinstance(data, str), 'integer': type(data) is int,
             'boolean': type(data) is bool, 'number': type(data) in (int, float)}
    if kind and not valid.get(kind, False):
        raise ValueError(path + ' 类型应为 ' + kind)
    if isinstance(data, float) and not math.isfinite(data):
        raise ValueError(path + ' 不允许非有限数字')
    if 'enum' in schema and data not in schema['enum']:
        raise ValueError(path + ' 不在可选值中')
    if kind == 'object':
        props = schema.get('properties', {})
        if set(schema.get('required', [])) - set(data):
            raise ValueError(path + ' 缺少必填参数')
        if schema.get('additionalProperties') is False and set(data) - set(props):
            raise ValueError(path + ' 含未知参数')
        for key, value in data.items():
            if key in props:
                validate_input(value, props[key], path + '.' + key)
    if kind == 'array':
        if len(data) < schema.get('minItems', 0) or len(data) > schema.get('maxItems', 1000000):
            raise ValueError(path + ' 数组长度超限')
        if schema.get('uniqueItems') and len({json.dumps(x, sort_keys=True) for x in data}) != len(data):
            raise ValueError(path + ' 存在重复项')
        for value in data:
            if 'items' in schema:
                validate_input(value, schema['items'], path + '[]')
    if kind == 'string':
        if len(data) < schema.get('minLength', 0) or ('pattern' in schema and not re.search(schema['pattern'], data)):
            raise ValueError(path + ' 字符串格式无效')
    if kind in ('integer', 'number'):
        if data < schema.get('minimum', -math.inf) or data > schema.get('maximum', math.inf):
            raise ValueError(path + ' 数字超出范围')


class Server:
    """实现初始化、工具发现、结构化结果与协议错误的最小 stdio 入口。"""

    def __init__(self, endpoint=DEFAULT_ENDPOINT, allow_write=False, output_root=None, native_factory=None):
        self.endpoint = validate_endpoint(endpoint)
        self.allow_write = allow_write
        self.output_root = output_root
        self.native_factory = native_factory or (lambda: NativeMcp(endpoint, timeout=15))
        self.initialized = False

    def execute(self, name, arguments):
        definition = next((t for t in TOOLS if t['name'] == name), None)
        if definition is None:
            raise ValueError('未知工具：' + str(name))
        validate_input(arguments, definition['inputSchema'])
        # 模式约束在连接原生服务前执行，避免关闭写入时仍触及原生调用。
        if name in {'easyeda_call_api', 'easyeda_auto_layout', 'easyeda_auto_route'} and not self.allow_write:
            raise ValueError('需要 --allow-write；只读模式没有执行该操作')
        if name == 'easyeda_export_manufacturing' and self.output_root is None:
            raise ValueError('需要 --output-root；没有执行文件导出')
        native = self.native_factory()
        workflows = Workflows(native, self.allow_write, self.output_root)
        if name == 'easyeda_doctor':
            return {'server': native.info['serverInfo'], 'bridge': native.call('doctor'),
                    'writeEnabled': self.allow_write, 'exportEnabled': self.output_root is not None}
        if name == 'easyeda_list_sessions':
            return {'sessions': native.call('session.list')}
        if name == 'easyeda_get_api':
            native.help('doc.api')
            return {'documentation': native.call('doc.api', {'className': arguments['class_name'],
                **({'methodName': arguments['method_name']} if 'method_name' in arguments else {})})}
        action = {'easyeda_inspect_project': workflows.inspect_project,
                  'easyeda_list_components': workflows.list_components,
                  'easyeda_read_netlist': workflows.read_netlist,
                  'easyeda_check_drc': workflows.check_drc,
                  'easyeda_call_api': workflows.call_api,
                  'easyeda_auto_layout': workflows.auto_layout,
                  'easyeda_auto_route': workflows.auto_route,
                  'easyeda_export_manufacturing': workflows.export_manufacturing}[name]
        return action(**arguments)

    def handle(self, message):
        request_id = message.get('id') if isinstance(message, dict) else None
        def response(result):
            return {'jsonrpc': '2.0', 'id': request_id, 'result': result}
        def error(code, text):
            return {'jsonrpc': '2.0', 'id': request_id, 'error': {'code': code, 'message': text}}
        if not isinstance(message, dict) or message.get('jsonrpc') != '2.0' or not isinstance(message.get('method'), str):
            return error(-32600, 'Invalid Request')
        if 'id' not in message:
            return None
        method = message['method']
        params = message.get('params', {})
        if not isinstance(params, dict):
            return error(-32602, 'params must be an object')
        if method == 'initialize':
            self.initialized = True
            return response({'protocolVersion': PROTOCOL, 'capabilities': {'tools': {}},
                             'serverInfo': {'name': 'easyeda-mcp', 'version': VERSION},
                             'instructions': '先 doctor、inspect_project；只操作明确 UUID。写入默认关闭，工程为空不创建。'})
        if method == 'ping':
            return response({})
        if not self.initialized:
            return error(-32000, 'Initialize first')
        if method == 'tools/list':
            return response({'tools': TOOLS})
        if method == 'tools/call':
            try:
                data = {'ok': True, 'result': self.execute(params.get('name'), params.get('arguments', {}))}
                json.dumps(data, allow_nan=False)
            except Exception as exc:
                data = {'ok': False, 'error': str(exc),
                        'nextStep': '核对连接、当前会话/文档和 API。写入超时或失败后先回读，不要盲目重试。'}
            return response({'isError': not data['ok'], 'structuredContent': data,
                             'content': [{'type': 'text', 'text': json.dumps(data, ensure_ascii=False, allow_nan=False)}]})
        return error(-32601, 'Method not found: ' + method)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint', default=DEFAULT_ENDPOINT)
    parser.add_argument('--allow-write', action='store_true')
    parser.add_argument('--output-root', type=Path)
    args = parser.parse_args()
    server = Server(args.endpoint, args.allow_write, args.output_root)
    for raw in sys.stdin.buffer:
        if len(raw) > 1024 * 1024:
            print('Request exceeds 1MiB', file=sys.stderr)
            return 1
        try:
            message = json.loads(raw, parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
            result = server.handle(message)
        except (ValueError, UnicodeError):
            result = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Parse error'}}
        if result is not None:
            print(json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
