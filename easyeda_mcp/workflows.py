"""工程、网表、布线和制造导出的确定性适配；编辑器仍是状态所有者。"""
import base64
import hashlib
import json
from pathlib import Path
import re
import zipfile


class WorkflowError(RuntimeError):
    """操作没有满足前置条件，或结果尚不能确认。"""


def literal(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class Workflows:
    """封装原生调用，不自动启动客户端、打开工程或保存用户工作。"""

    def __init__(self, native, allow_write=False, output_root=None):
        self.native = native
        self.allow_write = allow_write
        self.output_root = Path(output_root).resolve() if output_root else None

    def _write(self):
        if not self.allow_write:
            raise WorkflowError('当前为只读模式；已获用户修改授权后，需用 --allow-write 显式启动写入工具')

    def _context(self, document_uuid, session, kind=None):
        context = self.native.current_project(session)
        document = context.get('currentDocument')
        if context.get('project') is None or document is None:
            raise WorkflowError('没有当前工程/文档；在客户端打开目标工程和图页后重试')
        if document.get('uuid') != document_uuid:
            raise WorkflowError('当前焦点不是指定的目标文档；不会自动切换或打开工程')
        if kind and document.get('documentType') != {'schematic': 1, 'pcb': 3}[kind]:
            raise WorkflowError('目标文档类型不匹配：' + kind)
        return context

    def _run(self, document_uuid, session, body, apis=(), kind=None, timeout=30000):
        context = self._context(document_uuid, session, kind)
        for cls, method in apis:
            doc = self.native.call('doc.api', {'className': cls, 'methodName': method})
            if not isinstance(doc, dict) or 'returns' not in doc:
                raise WorkflowError('当前客户端缺少所需 API：' + cls + '.' + method)
        # 与业务操作放在同一次 invoke，收窄用户切换焦点造成的目标漂移窗口。
        project_uuid = context['project'].get('uuid')
        guard = ('const _doc=await eda.dmt_SelectControl.getCurrentDocumentInfo();'
                 'const _project=await eda.dmt_Project.getCurrentProjectInfo();'
                 f'if(!_doc||_doc.uuid!=={literal(document_uuid)}||!_project||'
                 f'_project.uuid!=={literal(project_uuid)}) return {{targetMatched: false}};')
        code = guard + 'const _value=await (async()=>{' + body + '})();return {targetMatched:true,value:_value};'
        self.native.help('invoke')
        previous_timeout = getattr(self.native, 'timeout', None)
        if previous_timeout is not None:
            self.native.timeout = timeout / 1000 + 5
        try:
            result = self.native.call('invoke', {'session': context['sessionId'], 'extUuid': 'eda',
                                                'timeout': timeout, 'code': code})
        finally:
            if previous_timeout is not None:
                self.native.timeout = previous_timeout
        if not isinstance(result, dict) or result.get('targetMatched') is not True:
            raise WorkflowError('调用时焦点已变化或目标校验未通过；停止操作，请重新读取工程')
        if 'value' not in result:
            raise WorkflowError('操作没有返回可确认结果；先回读，不自动重试')
        return result['value']

    def inspect_project(self, session=None):
        context = self.native.current_project(session)
        if context.get('project') is None or context.get('currentDocument') is None:
            return {**context, 'status': 'no_project'}
        apis = [('DMT_Board', 'getAllBoardsInfo'), ('DMT_Schematic', 'getAllSchematicPagesInfo'),
                ('DMT_Pcb', 'getAllPcbsInfo')]
        data = self._run(context['currentDocument']['uuid'], context['sessionId'],
                         'return {boards:await eda.dmt_Board.getAllBoardsInfo(),'
                         'schematicPages:await eda.dmt_Schematic.getAllSchematicPagesInfo(),'
                         'pcbs:await eda.dmt_Pcb.getAllPcbsInfo()};', apis)
        return {**context, 'documents': data}

    def list_components(self, document_uuid, kind, session=None, offset=0, limit=50):
        cls, mount = ('SCH_PrimitiveComponent', 'sch_PrimitiveComponent') if kind == 'schematic' else (
            'PCB_PrimitiveComponent', 'pcb_PrimitiveComponent')
        if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 200:
            raise WorkflowError('分页范围无效')
        body = f'const all=await eda.{mount}.getAll();const items=[];'
        body += f'for(const c of all.slice({offset},{offset + limit})){{items.push({{'
        fields = {'primitiveId': 'PrimitiveId', 'designator': 'Designator', 'x': 'X', 'y': 'Y', 'rotation': 'Rotation'}
        body += ','.join(k + ':await c.getState_' + v + '()' for k, v in fields.items())
        body += f'}});}}return {{items,total:all.length,offset:{offset},nextOffset:'
        body += f'{offset + limit}<all.length?{offset + limit}:null}};'
        data = self._run(document_uuid, session, body, [(cls, 'getAll')], kind)
        return {'kind': kind, 'coordinateUnit': '10mil' if kind == 'schematic' else 'mil',
                'note': '原理图列表可能包含网络旗标/端口；不是 BOM 数量', 'data': data}

    def read_netlist(self, document_uuid, session=None, offset=0, limit=20000):
        if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 100000:
            raise WorkflowError('文本分页范围无效')
        body = ('const file=await eda.sch_ManufactureData.getNetlistFile();'
                'if(!file) throw new Error("未生成网表，检查原理图网络与引脚编号");'
                'const text=await file.text();'
                f'return {{name:file.name,totalCharacters:text.length,text:text.slice({offset},{offset + limit}),'
                f'offset:{offset},nextOffset:{offset + limit}<text.length?{offset + limit}:null}};')
        return self._run(document_uuid, session, body, [('SCH_ManufactureData', 'getNetlistFile')], 'schematic')

    def check_drc(self, document_uuid, session=None):
        context = self._context(document_uuid, session)
        kind = {1: 'schematic', 3: 'pcb'}.get(context['currentDocument'].get('documentType'))
        if kind is None:
            raise WorkflowError('DRC 只支持当前原理图或 PCB 文档')
        cls, mount = ('SCH_Drc', 'sch_Drc') if kind == 'schematic' else ('PCB_Drc', 'pcb_Drc')
        result = self._run(document_uuid, context['sessionId'], f'return await eda.{mount}.check(true,false,false);',
                           [(cls, 'check')], kind, timeout=60000)
        if type(result) is not bool:
            raise WorkflowError('DRC 返回类型与当前支持的布尔模式不匹配')
        return {'kind': kind, 'passed': result, 'mode': 'strict', 'detailsIncluded': False}

    def auto_layout(self, document_uuid, session=None):
        self._write()
        result = self._run(document_uuid, session, 'return await eda.pcb_Document.autoLayout();',
                           [('PCB_Document', 'autoLayout')], 'pcb', timeout=300000)
        return {'status': 'returned', 'result': result, 'verification': '回读器件位置并执行 DRC；未自动保存'}

    def auto_route(self, document_uuid, nets=None, session=None):
        self._write()
        props = {} if nets is None else {'RoutingNets': nets}
        result = self._run(document_uuid, session, f'return await eda.pcb_Document.autoRouting({literal(props)});',
                           [('PCB_Document', 'autoRouting')], 'pcb', timeout=900000)
        return {'status': 'returned', 'result': result, 'verification': '保留 failedNets 等原始字段；需另行读取网络和 DRC'}

    def call_api(self, document_uuid, class_name, method_name, args, session=None):
        self._write()
        if not re.fullmatch(r'(?:DMT|SCH|PCB|LIB)_[A-Za-z0-9_]+', class_name):
            raise WorkflowError('通用调用只允许 DMT/SCH/PCB/LIB；系统文件、进程与网络接口不在此入口开放')
        if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]*', method_name) or method_name in ('constructor', '__proto__'):
            raise WorkflowError('方法名无效')
        meta = self.native.call('doc.api', {'className': class_name})
        mount = meta.get('callPath', '')
        if not re.fullmatch(r'(?:dmt|sch|pcb|lib)_[A-Za-z0-9_]+', mount):
            raise WorkflowError('当前文档没有明确可执行的 eda mount')
        if method_name not in {x['name'] for x in meta.get('methods', [])}:
            raise WorkflowError('当前客户端未列出该方法')
        kind = 'pcb' if class_name.startswith('PCB_') else ('schematic' if class_name.startswith('SCH_') else None)
        result = self._run(document_uuid, session,
                           f'const result=await eda.{mount}.{method_name}(...{literal(args)});'
                           'return {returned:result!==undefined,value:result??null};',
                           [(class_name, method_name)], kind)
        return {'status': 'returned', 'api': mount + '.' + method_name, 'result': result,
                'verification': '复杂图元/File 可能不可直接序列化；使用专用读取或导出工具核对。无自动重试。'}

    def export_manufacturing(self, document_uuid, destination, formats, session=None, prefix='Board'):
        if self.output_root is None:
            raise WorkflowError('未配置 --output-root，不执行文件导出')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,48}', prefix):
            raise WorkflowError('输出文件前缀只支持 1~48 个字母、数字、下划线或短横线')
        directory = (self.output_root / destination).resolve()
        if Path(destination).is_absolute() or not directory.is_relative_to(self.output_root):
            raise WorkflowError('输出目录超出 --output-root')
        kinds = {'gerber': ('getGerberFile', 'zip'), 'bom': ('getBomFile', 'csv'),
                 'pick_and_place': ('getPickAndPlaceFile', 'csv')}
        if not formats or len(set(formats)) != len(formats) or any(x not in kinds for x in formats):
            raise WorkflowError('制造文件格式无效或重复')
        targets = [(kind, directory / (prefix + '_' + kind + '.' + kinds[kind][1])) for kind in formats]
        if any(path.exists() or path.is_symlink() for _, path in targets):
            raise WorkflowError('输出文件已经存在；请使用新的目录或前缀，不会覆盖')
        files = []
        try:
            for kind, path in targets:
                method = kinds[kind][0]
                args = [prefix] if kind == 'gerber' else ([prefix, 'csv', 'mm'] if kind == 'pick_and_place' else [prefix, 'csv'])
                body = f'const f=await eda.pcb_ManufactureData.{method}(...{literal(args)});'
                body += ('if(!f||!f.size)throw new Error("未生成非空文件");'
                         'if(f.size>20971520)throw new Error("文件超过本版 20MiB 上限");'
                         'const b=new Uint8Array(await f.arrayBuffer());let s="";'
                         'for(let i=0;i<b.length;i+=8192)s+=String.fromCharCode(...b.subarray(i,i+8192));'
                         'return {name:f.name,size:f.size,base64:btoa(s)};')
                data = self._run(document_uuid, session, body, [('PCB_ManufactureData', method)], 'pcb', timeout=120000)
                raw = base64.b64decode(data['base64'], validate=True)
                if not raw or len(raw) != data['size'] or len(raw) > 20 * 1024 * 1024:
                    raise WorkflowError('实际导出字节数与文件属性不一致')
                directory.mkdir(parents=True, exist_ok=True)
                if not directory.resolve().is_relative_to(self.output_root):
                    raise WorkflowError('输出目录在生成过程中发生变化')
                with path.open('xb') as output:
                    output.write(raw)
                record = {'format': kind, 'path': str(path), 'bytes': len(raw),
                          'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                files.append(record)
                if kind == 'gerber':
                    with zipfile.ZipFile(path) as archive:
                        if archive.testzip() is not None:
                            raise WorkflowError('Gerber ZIP CRC 检查失败')
                        record['archiveEntries'] = archive.namelist()
            return {'status': 'generated', 'files': files,
                    'verification': '已核对字节与摘要；Gerber 检查 ZIP。电气、层/钻孔、坐标和制造可用性需另行预览。'}
        except Exception as error:
            raise WorkflowError('制造导出未完整完成；已落盘文件=' + literal(files) + '；原因=' + str(error)) from error
