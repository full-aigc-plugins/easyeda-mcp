"""检查传输来源、工具定义和基本包结构，不冒充设计验收。"""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from easyeda_mcp.server import TOOLS


def validate(root=ROOT):
    source = json.loads((root / 'docs/transport-source.json').read_text())
    if hashlib.sha256((root / 'easyeda_mcp/transport.py').read_bytes()).hexdigest() != source['sha256']:
        raise SystemExit('原生传输快照与来源摘要不一致')
    if len(TOOLS) != len({x['name'] for x in TOOLS}):
        raise SystemExit('工具名称重复')
    for tool in TOOLS:
        if tool['inputSchema']['additionalProperties'] is not False or 'annotations' not in tool:
            raise SystemExit('工具定义不完整')
    for path in root.rglob('*'):
        if any(part in path.parts for part in ('.local', 'dist', 'node_modules')):
            continue
        if path.is_symlink():
            raise SystemExit('包内不得通过符号链接依赖兄弟目录')
    return {'ok': True, 'tools': len(TOOLS), 'dependencies': 'Python standard library only'}


if __name__ == '__main__':
    print(json.dumps(validate()))
