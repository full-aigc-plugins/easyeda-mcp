#!/usr/bin/env python3
"""原生 MCP 的小型诊断客户端；不提供第二个 MCP 服务或工程写入接口。"""
import argparse
import ipaddress
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_ENDPOINT = 'http://127.0.0.1:31637/mcp'


class McpError(RuntimeError):
    """原生协议、会话或实际操作未成功。"""


def validate_endpoint(endpoint):
    """本地客户端只连接 loopback，不携带 URL 凭据。"""
    value = urllib.parse.urlsplit(endpoint)
    try:
        local = value.hostname == 'localhost' or ipaddress.ip_address(value.hostname).is_loopback
        port = value.port
    except (ValueError, TypeError):
        local = False
        port = None
    if value.scheme != 'http' or not local or value.username or value.password or value.fragment:
        raise ValueError('只允许无凭据、无 fragment 的本机 HTTP MCP 地址')
    if port is not None and not 1 <= port <= 65535:
        raise ValueError('端口超出范围')
    return endpoint


def unwrap(result):
    """同时检查 MCP 工具错误与原生命令内部错误。"""
    if result.get('isError'):
        raise McpError(json.dumps(result.get('content', []), ensure_ascii=False))
    structured = result.get('structuredContent')
    if structured is None:
        texts = [x['text'] for x in result.get('content', []) if x.get('type') == 'text']
        if len(texts) != 1:
            raise McpError('原生工具未返回单一 JSON 结果')
        try:
            structured = json.loads(texts[0])
        except ValueError as error:
            raise McpError('原生工具结果不是 JSON') from error
    if isinstance(structured, dict) and structured.get('ok') is False:
        raise McpError(json.dumps(structured.get('error', structured), ensure_ascii=False))
    if isinstance(structured, dict) and 'ok' in structured:
        return structured.get('data', structured.get('value'))
    return structured


class NativeMcp:
    """通过客户端内置的 Streamable HTTP 发现真实工具名。"""

    def __init__(self, endpoint=DEFAULT_ENDPOINT, timeout=15):
        self.endpoint = validate_endpoint(endpoint)
        self.timeout = timeout
        self.sequence = 0
        # 不允许请求重定向到另一服务或远程地址。
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                raise McpError('MCP 地址发生重定向，已停止')
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        self.info = self.rpc('initialize', {
            'protocolVersion': '2025-06-18', 'capabilities': {},
            'clientInfo': {'name': 'easyeda-skills-diagnostics', 'version': '0.1.0'},
        })
        identity = self.info.get('serverInfo', {})
        if identity.get('name') not in ('JLCEDA Pro', 'EasyEDA Pro'):
            raise McpError('该地址不是官方 EDA 原生 MCP 服务')
        self.tools = self.rpc('tools/list', {}).get('tools', [])
        self.tool_names = {}
        for suffix in ('help', 'discover', 'call'):
            matches = [x['name'] for x in self.tools if x['name'].endswith('.' + suffix)]
            if len(matches) != 1:
                raise McpError('无法唯一发现原生 ' + suffix + ' 工具')
            self.tool_names[suffix] = matches[0]
        self.help()

    def rpc(self, method, params):
        """发送有期限的本地 JSON-RPC 请求。"""
        self.sequence += 1
        request = urllib.request.Request(self.endpoint, data=json.dumps({
            'jsonrpc': '2.0', 'id': self.sequence, 'method': method, 'params': params,
        }).encode(), headers={
            'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream',
            'MCP-Protocol-Version': '2025-06-18',
        })
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                message = json.load(response)
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            raise McpError('本地 MCP 请求失败：' + str(error)) from error
        if 'error' in message:
            raise McpError(json.dumps(message['error'], ensure_ascii=False))
        if message.get('id') != self.sequence or 'result' not in message:
            raise McpError('MCP 响应 ID 或结果不匹配')
        return message['result']

    def help(self, path=None):
        return unwrap(self.rpc('tools/call', {
            'name': self.tool_names['help'], 'arguments': {} if path is None else {'path': path},
        }))

    def call(self, path, data=None):
        return unwrap(self.rpc('tools/call', {
            'name': self.tool_names['call'], 'arguments': {'path': path, 'input': data or {}},
        }))

    def current_project(self, session=None):
        """只读当前工程；多会话不猜测，空工程也不伪装成成功读取。"""
        sessions = [x for x in self.call('session.list') if x.get('status') == 'alive']
        selected = [x for x in sessions if x.get('sessionId') == session] if session else sessions
        if not selected:
            raise McpError('没有符合条件的编辑器会话；请打开目标工程后重试')
        if len(selected) != 1:
            raise McpError('存在多个编辑器会话，请显式提供 --session')
        sid = selected[0]['sessionId']
        self.help('invoke')
        result = self.call('invoke', {
            'session': sid, 'extUuid': 'eda', 'timeout': 15000,
            'code': 'return {project: (await eda.dmt_Project.getCurrentProjectInfo()) ?? null, '
                    'currentDocument: (await eda.dmt_SelectControl.getCurrentDocumentInfo()) ?? null};',
        })
        if not isinstance(result, dict) or 'project' not in result:
            raise McpError('原生 API 未返回工程状态')
        return {'status': 'no_project' if result['project'] is None else 'read',
                'sessionId': sid, **result}


def start_native(endpoint, app=None):
    """显式启动原生服务；已有服务时复用，不安装任何软件。"""
    endpoint = validate_endpoint(endpoint)
    try:
        return NativeMcp(endpoint).info
    except McpError as error:
        # 占用端口却身份不符时不再启动第二个进程。
        if '请求失败' not in str(error):
            raise
    port = urllib.parse.urlsplit(endpoint).port or 80
    if sys.platform == 'darwin':
        target = app or next((p for p in [
            '/Applications/嘉立创EDA(专业版).app', '/Applications/EasyEDA Pro.app',
        ] if os.path.isdir(p)), None)
        if not target:
            raise McpError('未找到客户端，请通过 --app 指定已安装的 .app 路径')
        subprocess.run(['/usr/bin/open', '-n', '-a', target, '--args', '--mcp', 'http',
                        '--host', '127.0.0.1', '--port', str(port)], check=True)
    else:
        executable = app or shutil.which('lceda-pro') or shutil.which('easyeda-pro')
        if not executable:
            raise McpError('未找到客户端 CLI，请指定 --app；本脚本不会安装客户端')
        subprocess.Popen([executable, '--mcp', 'http', '--host', '127.0.0.1', '--port', str(port)],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            return NativeMcp(endpoint, timeout=2).info
        except McpError:
            time.sleep(0.5)
    raise McpError('客户端 MCP 未在期限内就绪，请检查应用启动或权限提示')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint', default=DEFAULT_ENDPOINT)
    parser.add_argument('--session')
    parser.add_argument('--app')
    parser.add_argument('operation', choices=['start', 'doctor', 'sessions', 'current-project', 'api-help'])
    parser.add_argument('--class-name')
    parser.add_argument('--method-name')
    args = parser.parse_args()
    try:
        if args.operation == 'start':
            result = start_native(args.endpoint, args.app)
        else:
            client = NativeMcp(args.endpoint)
            if args.operation == 'doctor':
                result = {'server': client.info['serverInfo'], 'bridge': client.call('doctor'),
                          'tools': list(client.tool_names.values())}
            elif args.operation == 'sessions':
                result = client.call('session.list')
            elif args.operation == 'current-project':
                result = client.current_project(args.session)
            else:
                client.help('doc.api')
                result = client.call('doc.api', {k: v for k, v in {
                    'className': args.class_name, 'methodName': args.method_name,
                }.items() if v is not None})
        print(json.dumps({'ok': True, 'result': result}, ensure_ascii=False))
    except (McpError, ValueError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
