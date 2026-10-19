"""协议发现、入参拒绝和标准 stdio 子进程验证。"""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from easyeda_mcp.server import Server, TOOLS

ROOT = Path(__file__).resolve().parents[1]


class ProtocolTests(unittest.TestCase):
    def request(self, method, params=None):
        return {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}}

    def test_initialize_and_list_without_native_connection(self):
        server = Server(native_factory=lambda: self.fail('初始化或发现不应连接原生客户端'))
        self.assertEqual(server.handle(self.request('tools/list'))['error']['code'], -32000)
        self.assertEqual(server.handle(self.request('initialize'))['result']['serverInfo']['name'], 'easyeda-mcp')
        self.assertIsNone(server.handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'}))
        tools = server.handle(self.request('tools/list'))['result']['tools']
        self.assertEqual(len(tools), 11)
        self.assertTrue(all('inputSchema' in t and 'outputSchema' in t and 'annotations' in t for t in tools))

    def test_invalid_input_never_reaches_native(self):
        server = Server(native_factory=lambda: self.fail('错误入参不得连接原生客户端'))
        server.handle(self.request('initialize'))
        for args in [dict(document_uuid='x', kind='pcb', limit=201),
                     dict(document_uuid='x', kind='pcb', limit=True),
                     dict(document_uuid='x', kind='pcb', unknown=1)]:
            result = server.handle(self.request('tools/call', {'name': 'easyeda_list_components', 'arguments': args}))['result']
            self.assertTrue(result['isError'])
            self.assertFalse(result['structuredContent']['ok'])

    def test_write_and_export_modes_checked_before_connect(self):
        server = Server(native_factory=lambda: self.fail('模式未授权不应连接原生客户端'))
        for name, args in [('easyeda_auto_route', {'document_uuid': 'x'}),
                           ('easyeda_export_manufacturing', {'document_uuid': 'x', 'destination': 'out', 'formats': ['gerber']})]:
            with self.assertRaisesRegex(ValueError, '需要 --'):
                server.execute(name, args)

    def test_stdio_is_json_lines_and_handles_parse_error(self):
        messages = '\n'.join([json.dumps(self.request('initialize')),
                              json.dumps({'jsonrpc': '2.0', 'method': 'notifications/initialized'}),
                              json.dumps(self.request('tools/list')), '{bad',
                              json.dumps(self.request('unknown'))]) + '\n'
        result = subprocess.run([sys.executable, '-B', '-m', 'easyeda_mcp'], cwd=ROOT,
                                input=messages, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[2]['error']['code'], -32700)
        self.assertEqual(lines[3]['error']['code'], -32601)

    def test_output_schema_allows_success_and_failure_envelopes(self):
        self.assertEqual(len({x['name'] for x in TOOLS}), 11)
        for tool in TOOLS:
            self.assertEqual(tool['outputSchema']['required'], ['ok'])


if __name__ == '__main__':
    unittest.main()
