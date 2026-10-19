"""复验独立 LED 测试的实际网表与制造文件，并渲染本次 C/R 光圈 Gerber。"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

EXPECTED = {'J1': {'1': 'VCC', '2': 'GND'}, 'R1': {'1': 'VCC', '2': 'LED_A'}, 'D1': {'1': 'LED_A', '2': 'GND'}}


def render_layer(source, color):
    """只接受本测试导出的 MM / 4.5 / G01 / C、R 光圈子集，不推断未知几何。"""
    assert '%MOMM*%' in source and '%FSLAX45Y45*%' in source
    assert not re.search(r'(?:G0[23]|G3[67])(?:X|\*)', source), '遇到本测试渲染器不支持的弧线或区域'
    apertures = {}
    for ident, shape, params in re.findall(r'%ADD(\d+)([^,]+),([^*]+)\*%', source):
        assert shape in {'C', 'R'}, '不支持该光圈：' + shape
        apertures[int(ident)] = (shape, [float(v) for v in params.split('X')])
    items, points, aperture = [], [], None
    x = y = 0.0
    for line in source.splitlines():
        select = re.fullmatch(r'(?:G54)?D(\d+)\*', line)
        if select:
            aperture = apertures[int(select[1])]
            continue
        op = re.fullmatch(r'(?:G01)?X(-?\d+)Y(-?\d+)D(0[123])\*', line)
        if not op:
            assert not re.match(r'(?:G0[123])?[XY]', line), '未解析的坐标命令：' + line
            continue
        nx, ny, action = int(op[1]) / 100000, int(op[2]) / 100000, op[3]
        points.append((nx, ny))
        assert aperture is not None
        shape, size = aperture
        if action == '01':
            assert shape == 'C'
            items.append(f'<path d="M{x},{y} L{nx},{ny}" stroke="{color}" stroke-width="{size[0]}" stroke-linecap="round" fill="none"/>')
        elif action == '03':
            if shape == 'C':
                items.append(f'<circle cx="{nx}" cy="{ny}" r="{size[0]/2}" fill="{color}"/>')
            else:
                items.append(f'<rect x="{nx-size[0]/2}" y="{ny-size[1]/2}" width="{size[0]}" height="{size[1]}" fill="{color}"/>')
        x, y = nx, ny
    return ''.join(items), points


def verify(directory):
    netlist = json.loads((directory / 'schematic-netlist.json').read_text())
    actual = {c['props']['Designator']: {k: p['net'] for k, p in c['pinInfoMap'].items()} for c in netlist['components'].values()}
    assert actual == EXPECTED, actual
    pcb = json.loads((directory / 'records/pcb-pads.json').read_text())['result']['items']
    pcb_by_name = {c['designator']: c for c in pcb}
    assert {name: {p['number']: p['net'] for p in c['pads']} for name, c in pcb_by_name.items()} == EXPECTED
    reopened = json.loads((directory / 'reopen-validation.json').read_text())
    assert reopened['pcb']['lines'] == 6 and len(reopened['pcb']['components']) == 3
    assert reopened['drc']['data']['passed'] and reopened['schematicDrc']['data']['passed']
    assert reopened['capabilities']['data']['writeEnabled'] is False
    assert reopened['schematicConnectionsMatch']
    report = {'netlistPassed': True, 'pcbPinNetsPassed': True, 'reopenPassed': True, 'csv': {}}
    for kind in ['bom', 'pickAndPlace']:
        raw = (directory / f'EasyEDA_LED_Test_{kind}.csv').read_bytes()
        assert raw.startswith(b'\xff\xfe')
        rows = [r for r in csv.DictReader(io.StringIO(raw.decode('utf-16')), delimiter='\t') if any(r.values())]
        assert {r['Designator'] for r in rows} == set(EXPECTED)
        if kind == 'bom':
            assert sum(int(r['Quantity']) for r in rows) == 3
            assert {r['Designator']: r['Supplier Part'] for r in rows} == {'J1': 'C124375', 'R1': 'C21190', 'D1': 'C2986060'}
        else:
            for row in rows:
                native = pcb_by_name[row['Designator']]
                assert abs(float(row['Mid X'].removesuffix('mm')) - native['x'] * .0254) < .001
                assert abs(float(row['Mid Y'].removesuffix('mm')) - native['y'] * .0254) < .001
        report['csv'][kind] = {'rows': len(rows), 'encoding': 'UTF-16LE', 'delimiter': 'TAB'}
    required = {'Gerber_TopLayer.GTL', 'Gerber_BottomLayer.GBL', 'Gerber_TopSilkscreenLayer.GTO', 'Gerber_TopSolderMaskLayer.GTS', 'Gerber_BottomSolderMaskLayer.GBS', 'Gerber_BoardOutlineLayer.GKO', 'Drill_PTH_Through.DRL'}
    with zipfile.ZipFile(directory / 'EasyEDA_LED_Test_gerber.zip') as archive:
        assert archive.testzip() is None
        assert required <= set(archive.namelist())
        outline, points = render_layer(archive.read('Gerber_BoardOutlineLayer.GKO').decode(), '#b6ccdf')
        assert points[0] == points[-1]
        assert {x for x, _ in points} == {0, 25.4}
        assert {y for _, y in points} == {0, 20.32}
        copper, copper_points = render_layer(archive.read('Gerber_TopLayer.GTL').decode(), '#ec9566')
        silk, _ = render_layer(archive.read('Gerber_TopSilkscreenLayer.GTO').decode(), '#f7f3d8')
        drill = archive.read('Drill_PTH_Through.DRL').decode()
        diameter = float(re.search(r'T01C([\d.]+)', drill)[1])
        holes = [(float(x), float(y)) for x, y in re.findall(r'^X([\d.]+)Y([\d.]+)$', drill, re.M)]
        assert len(holes) == 2 and abs(diameter - 1.1) < .001
        assert all(0 < x < 25.4 and 0 < y < 20.32 for x, y in copper_points + holes)
        holes_svg = ''.join(f'<circle cx="{x}" cy="{y}" r="{diameter/2}" fill="#102335"/>' for x, y in holes)
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="1024" viewBox="-1 -1 27.4 22.32"><rect x="-1" y="-1" width="27.4" height="22.32" fill="#102335"/><g transform="translate(0,20.32) scale(1,-1)"><rect width="25.4" height="20.32" fill="#13514a" rx=".06"/>{copper}{silk}{holes_svg}{outline}</g></svg>'''
        (directory / 'gerber-top-preview.svg').write_text(svg)
        report['gerber'] = {'entries': len(archive.namelist()), 'requiredLayersPresent': True, 'boardSizeMm': [25.4, 20.32], 'platedHoles': len(holes), 'drillDiameterMm': diameter, 'preview': 'gerber-top-preview.svg', 'previewScope': 'actual top copper + top silkscreen + outline + plated drill, strict G01 C/R subset'}
    report['sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir() if p.is_file() and p.name != 'EasyEDA_LED_Test_delivery.zip' and p.suffix in {'.zip', '.csv', '.epro2'}}
    (directory / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    print(json.dumps(verify(parser.parse_args().directory), ensure_ascii=False))
