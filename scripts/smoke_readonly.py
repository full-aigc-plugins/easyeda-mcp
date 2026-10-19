"""通过真实 stdio 子进程只读验证原生连接；不会创建、修改或导出工程。"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import select
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def run(endpoint=None):
    command = [sys.executable, '-B', str(ROOT / 'scripts/serve.py')]
    if endpoint:
        command += ['--endpoint', endpoint]
    process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    sequence = 0
    def rpc(method, params):
        nonlocal sequence
        sequence += 1
        process.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': sequence, 'method': method, 'params': params}) + '\n')
        process.stdin.flush()
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if select.select([process.stdout], [], [], 1)[0]:
                line = process.stdout.readline()
                if not line:
                    raise RuntimeError('MCP 子进程提前退出')
                response = json.loads(line)
                if response.get('id') == sequence:
                    if 'error' in response:
                        raise RuntimeError(str(response['error']))
                    return response['result']
        raise TimeoutError('MCP 子进程只读调用超时')
    try:
        init = rpc('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
                                  'clientInfo': {'name': 'easyeda-readonly-smoke', 'version': '0.1.0'}})
        process.stdin.write(json.dumps({'jsonrpc': '2.0', 'method': 'notifications/initialized'}) + '\n')
        process.stdin.flush()
        tools = rpc('tools/list', {})['tools']
        results = {}
        for name, arguments in [('easyeda_doctor', {}), ('easyeda_list_sessions', {}),
                                ('easyeda_inspect_project', {}),
                                ('easyeda_get_api', {'class_name': 'PCB_Document', 'method_name': 'autoRouting'})]:
            reply = rpc('tools/call', {'name': name, 'arguments': arguments})
            data = reply['structuredContent']
            if reply.get('isError') or not data['ok']:
                raise RuntimeError(name + ': ' + str(data))
            results[name] = data['result']
        # 模式拦截亦通过真实 stdio 检查；即使工程存在也不会触及写入。
        blocked = rpc('tools/call', {'name': 'easyeda_auto_route', 'arguments': {'document_uuid': 'read-only-probe'}})
        if not blocked.get('isError') or '--allow-write' not in blocked['structuredContent'].get('error', ''):
            raise RuntimeError('写入模式拦截未生效')
        return {'testedAt': datetime.now(timezone.utc).isoformat(), 'transport': 'real-stdio-subprocess',
                'server': init['serverInfo'], 'toolCount': len(tools), 'readOnly': True,
                'writeModeBlocked': True, 'results': results,
                'notRun': ['project mutations', 'layout/routing execution', 'DRC on actual board',
                           'manufacturing export on actual board', 'model task routing']}
    finally:
        process.terminate()
        process.wait(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = run(args.endpoint)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'ok': True, 'toolCount': result['toolCount'],
                      'projectStatus': result['results']['easyeda_inspect_project']['status'],
                      'writeModeBlocked': result['writeModeBlocked']}, ensure_ascii=False))
