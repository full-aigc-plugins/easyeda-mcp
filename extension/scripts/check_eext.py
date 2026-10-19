"""检查 .eext 的真实 ZIP 内容、入口、菜单和源码捆绑边界。"""
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def check():
    manifest = json.loads((ROOT / 'extension.json').read_text())
    target = ROOT / 'build/dist' / (manifest['name'] + '_v' + manifest['version'] + '.eext')
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP CRC 校验失败')
        files = set(archive.namelist())
        required = {'extension.json', 'dist/index.js', 'iframe/index.html', 'iframe/panel.js',
                    'iframe/panel.css', 'LICENSE', 'NOTICE', 'README.md', 'docs/native-mcp.md'}
        if not required <= files:
            raise ValueError('扩展包缺少必要文件：' + str(required - files))
        if any(name.startswith(('node_modules/', 'src/', 'tests/', 'build/', 'config/', 'scripts/')) for name in files):
            raise ValueError('扩展包含不应随包分发的开发工具/源码')
        packed = json.loads(archive.read('extension.json'))
        if packed != manifest or not re.fullmatch('[a-f0-9]{32}', packed['uuid']):
            raise ValueError('打包 manifest 不一致或 UUID 无效')
        identifiers = []
        for menus in manifest['headerMenus'].values():
            for menu in menus:
                identifiers.append(menu['id'])
                identifiers.extend(item['id'] for item in menu['menuItems'])
        if len(identifiers) != len(set(identifiers)):
            raise ValueError('菜单 ID 不唯一')
        script = archive.read('dist/index.js').decode()
        if 'edaEsbuildExportName' not in script or 'sys_ExternalApi.register' not in script:
            raise ValueError('没有 SDK IIFE 入口或 External API 注册代码')
        for export in ['openPanel', 'enableWrites', 'disableWrites', 'activate']:
            if not re.search(r'\b' + export + r'\b', script):
                raise ValueError('菜单/激活函数缺失：' + export)
        for name in ['dist/index.js', 'README.md', 'iframe/index.html', 'iframe/panel.js', 'iframe/panel.css']:
            if archive.read(name) != (ROOT / name).read_bytes():
                raise ValueError('安装包与当前文件不一致：' + name)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.eext.sha256').write_text(digest + '  ' + target.name + '\n')
    return {'ok': True, 'path': str(target), 'uuid': manifest['uuid'], 'version': manifest['version'],
            'files': len(files), 'sha256': digest, 'scope': 'archive_integrity_only'}


if __name__ == '__main__':
    print(json.dumps(check(), ensure_ascii=False))
