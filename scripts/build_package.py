"""生成可移交的本地 ZIP；不发布、不安装、不修改宿主配置。"""
import hashlib
import json
from pathlib import Path
import zipfile
from validate_package import validate

ROOT = Path(__file__).resolve().parents[1]


def build(root=ROOT):
    validate(root)
    version = '0.1.0-dev.20261019.1'
    target = root / 'dist' / ('easyeda-mcp-' + version + '.zip')
    target.parent.mkdir(exist_ok=True)
    count = 0
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob('*')):
            parts = path.relative_to(root).parts
            if any(p in {'.git', '.local', 'dist', 'node_modules', '__pycache__', '.DS_Store'} for p in parts):
                continue
            if path.is_symlink():
                raise ValueError('打包路径不得包含符号链接：' + str(path))
            if not path.is_file() or path.suffix == '.pyc':
                continue
            record = zipfile.ZipInfo('/'.join(parts), date_time=(2026, 10, 19, 0, 0, 0))
            record.compress_type = zipfile.ZIP_DEFLATED
            record.external_attr = 0o100644 << 16
            archive.writestr(record, path.read_bytes())
            count += 1
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP CRC 校验失败')
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.zip.sha256').write_text(digest + '  ' + target.name + '\n')
    return {'ok': True, 'path': str(target), 'files': count, 'sha256': digest}


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False))
