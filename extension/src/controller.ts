import { base64, DomainError, list, number, object, page, text } from './validation';
export interface Policy {
    writeEnabled: boolean;
}
type EditorApi = typeof eda;
/** 编辑器拥有状态，本层只做目标检查、参数适配与结果提取。 */
export function createController(api: EditorApi, policy: Policy = { writeEnabled: false }) {
    function requireWrite() {
        if (!policy.writeEnabled)
            throw new DomainError('READ_ONLY', '请在 EasyEDA MCP 菜单或面板中开启工程修改');
    }
    async function context(allowDocumentFallback: boolean) {
        const document = await api.dmt_SelectControl.getCurrentDocumentInfo();
        let timer: ReturnType<typeof setTimeout> | undefined;
        let project;
        let warning: string | undefined;
        try {
            project = await Promise.race([
                api.dmt_Project.getCurrentProjectInfo(),
                new Promise<never>((_, reject) => {
                    timer = setTimeout(() => reject(new DomainError('SDK_TIMEOUT', '客户端工程信息 API 超过 1500ms；原始只读调用可能仍在等待')), 1500);
                }),
            ]);
        } catch (error) {
            if (!allowDocumentFallback || !document?.parentProjectUuid) throw error;
            // 仅只读可使用活动文档明确返回的父工程身份，不推测工程名称。
            project = { uuid: document.parentProjectUuid };
            warning = String(error);
        } finally {
            if (timer !== undefined) clearTimeout(timer);
        }
        if (!project && allowDocumentFallback && document?.parentProjectUuid) {
            project = { uuid: document.parentProjectUuid };
            warning = '工程信息 API 没有返回工程；使用活动文档提供的父工程 UUID';
        }
        return {project, document, projectInfoSource: warning ? 'active_document' : 'project_api', warnings: warning ? [warning] : []};
    }
    async function focus(input: Record<string, unknown>, kind?: 'schematic' | 'pcb', allowDocumentFallback = true) {
        const projectUuid = text(input.projectUuid, 'projectUuid'), documentUuid = text(input.documentUuid, 'documentUuid');
        const {project, document} = await context(allowDocumentFallback);
        if (!project || !document)
            throw new DomainError('NO_PROJECT', '没有当前工程或活动图页');
        if (project.uuid !== projectUuid || document.uuid !== documentUuid || (document.parentProjectUuid && document.parentProjectUuid !== projectUuid))
            throw new DomainError('TARGET_CHANGED', '当前工程/文档与指定 UUID 不一致，请重新读取');
        if ((kind === 'schematic' && document.documentType !== 1) || (kind === 'pcb' && document.documentType !== 3))
            throw new DomainError('WRONG_DOCUMENT', `当前文档不是 ${kind}`);
        return { project, document };
    }
    async function inspectProject(raw: unknown = {}) {
        object(raw);
        const {project, document: currentDocument, projectInfoSource, warnings} = await context(true);
        if (!project)
            return { status: 'no_project', project: null, currentDocument: currentDocument ?? null };
        const boards = await api.dmt_Board.getAllBoardsInfo(), schematicPages = await api.dmt_Schematic.getAllSchematicPagesInfo(), pcbs = await api.dmt_Pcb.getAllPcbsInfo();
        const afterDocument = await api.dmt_SelectControl.getCurrentDocumentInfo();
        if (afterDocument?.uuid !== currentDocument?.uuid || afterDocument?.parentProjectUuid !== currentDocument?.parentProjectUuid) {
            throw new DomainError('TARGET_CHANGED', '读取工程目录时焦点发生变化，请重新读取');
        }
        if (projectInfoSource === 'project_api') {
            const after = await context(false);
            if (after.project?.uuid !== project.uuid) throw new DomainError('TARGET_CHANGED', '读取工程目录时工程发生变化');
        }
        return { status: currentDocument ? 'read' : 'project_only', project, currentDocument: currentDocument ?? null, boards, schematicPages, pcbs, projectInfoSource, warnings };
    }
    async function getCapabilities(raw: unknown = {}) {
        object(raw);
        return { namespace: 'easyedaMcp', writeEnabled: policy.writeEnabled, coordinateUnits: { schematic: '10mil', pcb: 'mil' }, autoLayout: typeof api.pcb_Document.autoLayout === 'function', autoRoute: typeof api.pcb_Document.autoRouting === 'function', exportDelivery: ['base64', 'dialog', 'filesystem'], compatibility: 'SDK 0.4.26；活动文档和自动布局/布线等含 Beta API，需目标客户端验收' };
    }
    async function listComponents(raw: unknown) {
        const input = object(raw), { offset, limit } = page(input), { document } = await focus(input);
        if (document.documentType !== 1 && document.documentType !== 3)
            throw new DomainError('WRONG_DOCUMENT', '仅支持原理图或 PCB');
        const all = document.documentType === 1 ? await api.sch_PrimitiveComponent.getAll() : await api.pcb_PrimitiveComponent.getAll();
        const items = all.slice(offset, offset + limit).map(c => ({ primitiveId: c.getState_PrimitiveId(), designator: c.getState_Designator(), x: c.getState_X(), y: c.getState_Y(), rotation: c.getState_Rotation() }));
        await focus(input);
        return { items, total: all.length, offset, nextOffset: offset + limit < all.length ? offset + limit : null, coordinateUnit: document.documentType === 1 ? '10mil' : 'mil', note: '原理图列表可能包含旗标/端口，不能直接作为 BOM 数量' };
    }
    async function getPins(raw: unknown) {
        const input = object(raw);
        await focus(input, 'schematic');
        const primitiveId = text(input.primitiveId, 'primitiveId'), pins = await api.sch_PrimitiveComponent.getAllPinsByPrimitiveId(primitiveId);
        if (!pins)
            throw new DomainError('NOT_FOUND', '找不到目标器件引脚');
        const items = pins.map(p => ({ pinNumber: p.getState_PinNumber(), pinName: p.getState_PinName(), x: p.getState_X(), y: p.getState_Y(), rotation: p.getState_Rotation(), noConnected: p.getState_NoConnected() }));
        await focus(input, 'schematic');
        return { primitiveId, coordinateUnit: '10mil', items };
    }
    async function searchDevices(raw: unknown) {
        const input = object(raw), query = text(input.query, 'query'), limit = input.limit === undefined ? 20 : number(input.limit, 'limit'), pageNumber = input.page === undefined ? 1 : number(input.page, 'page');
        if (!Number.isInteger(limit) || limit < 1 || limit > 100 || !Number.isInteger(pageNumber) || pageNumber < 1)
            throw new DomainError('BAD_INPUT', '器件检索分页无效');
        const items = await api.lib_Device.search(query, undefined, undefined, undefined, limit, pageNumber);
        return { items, page: pageNumber, limit, hasMore: items.length === limit };
    }
    async function getNetlist(raw: unknown) {
        const input = object(raw), { offset, limit } = page(input, 100000);
        await focus(input, 'schematic');
        const file = await api.sch_ManufactureData.getNetlistFile();
        if (!file)
            throw new DomainError('NETLIST_FAILED', '没有生成网表，检查器件引脚与连通性');
        const content = await file.text();
        await focus(input, 'schematic');
        return { name: file.name, text: content.slice(offset, offset + limit), totalCharacters: content.length, offset, nextOffset: offset + limit < content.length ? offset + limit : null };
    }
    async function checkDrc(raw: unknown) {
        const input = object(raw), { document } = await focus(input);
        if (document.documentType !== 1 && document.documentType !== 3)
            throw new DomainError('WRONG_DOCUMENT', '仅支持原理图/PCB DRC');
        const errors: unknown = document.documentType === 1 ? await api.sch_Drc.check(true, false, true) : await api.pcb_Drc.check(true, false, true);
        if (!Array.isArray(errors))
            throw new DomainError('INVALID_RESULT', '详细 DRC 结果应为数组');
        await focus(input);
        return { passed: errors.length === 0, total: errors.length, violations: errors, strict: true };
    }
    function placements(input: Record<string, unknown>) {
        // 整批输入先验证，再开始实际创建。
        const items = list(input.components, 'components').map(raw => {
            const c = object(raw);
            return { libraryUuid: text(c.libraryUuid, 'libraryUuid'), deviceUuid: text(c.deviceUuid, 'deviceUuid'), x: number(c.x, 'x'), y: number(c.y, 'y'), rotation: c.rotation === undefined ? 0 : number(c.rotation, 'rotation'), designator: c.designator === undefined ? undefined : text(c.designator, 'designator'), layer: c.layer === undefined ? 1 : number(c.layer, 'layer') };
        });
        const names = items.filter(c => c.designator !== undefined).map(c => c.designator);
        if (new Set(names).size !== names.length)
            throw new DomainError('BAD_INPUT', '批次内位号重复');
        return items;
    }
    async function placeSchematicComponents(raw: unknown) {
        requireWrite();
        const input = object(raw), items = placements(input);
        await focus(input, 'schematic', false);
        const created: Array<{
            primitiveId: string;
            designator: string | null;
        }> = [];
        try {
            for (const item of items) {
                await focus(input, 'schematic', false);
                const c = await api.sch_PrimitiveComponent.create({ libraryUuid: item.libraryUuid, uuid: item.deviceUuid }, item.x, item.y, undefined, item.rotation, false, true, true);
                if (!c)
                    throw new Error('SDK 未返回已创建器件');
                created.push({ primitiveId: c.getState_PrimitiveId(), designator: c.getState_Designator() ?? null });
                if (item.designator) {
                    const update = c.toAsync();
                    update.setState_Designator(item.designator);
                    await update.done();
                    created[created.length - 1].designator = item.designator;
                }
            }
            await focus(input, 'schematic', false);
            return { created, coordinateUnit: '10mil', saved: false };
        }
        catch (error) {
            throw new DomainError('PARTIAL_CHANGE', String(error), created);
        }
    }
    async function placePcbComponents(raw: unknown) {
        requireWrite();
        const input = object(raw), items = placements(input);
        if (items.some(c => c.layer !== 1 && c.layer !== 2))
            throw new DomainError('BAD_INPUT', '器件层仅支持顶层 1、底层 2');
        await focus(input, 'pcb', false);
        const created: string[] = [];
        try {
            for (const item of items) {
                await focus(input, 'pcb', false);
                const c = await api.pcb_PrimitiveComponent.create({ libraryUuid: item.libraryUuid, uuid: item.deviceUuid }, item.layer as 1 | 2, item.x, item.y, item.rotation, false);
                if (!c)
                    throw new Error('SDK 未返回已创建器件');
                created.push(c.getState_PrimitiveId());
                if (item.designator) {
                    const update = c.toAsync();
                    update.setState_Designator(item.designator);
                    await update.done();
                }
            }
            await focus(input, 'pcb', false);
            return { created, coordinateUnit: 'mil', saved: false };
        }
        catch (error) {
            throw new DomainError('PARTIAL_CHANGE', String(error), created);
        }
    }
    async function connectPins(raw: unknown) {
        requireWrite();
        const input = object(raw), from = object(input.from), to = object(input.to), netName = text(input.netName, 'netName');
        const a = { id: text(from.primitiveId, 'from.primitiveId'), pin: text(from.pinNumber, 'from.pinNumber') }, b = { id: text(to.primitiveId, 'to.primitiveId'), pin: text(to.pinNumber, 'to.pinNumber') };
        if (a.id === b.id && a.pin === b.pin)
            throw new DomainError('BAD_INPUT', '同一引脚不能连接自身');
        await focus(input, 'schematic', false);
        const findPin = async (id: string, pinNumber: string) => {
            const all = await api.sch_PrimitiveComponent.getAllPinsByPrimitiveId(id), matches = all?.filter(p => p.getState_PinNumber() === pinNumber) ?? [];
            if (matches.length !== 1)
                throw new DomainError('NOT_FOUND', '器件引脚不存在或编号不唯一');
            return { x: matches[0].getState_X(), y: matches[0].getState_Y() };
        };
        const start = await findPin(a.id, a.pin), end = await findPin(b.id, b.pin);
        const points = input.waypoints === undefined ? [] : list(input.waypoints, 'waypoints', 50).map(p => { const v = object(p); return { x: number(v.x, 'waypoint.x'), y: number(v.y, 'waypoint.y') }; });
        const vertices = points.length ? [start, ...points, end] : (start.x === end.x || start.y === end.y ? [start, end] : [start, { x: end.x, y: start.y }, end]);
        if (vertices.some((p, i) => i > 0 && p.x !== vertices[i - 1].x && p.y !== vertices[i - 1].y))
            throw new DomainError('BAD_INPUT', '连线必须正交，请提供合适的 waypoints');
        await focus(input, 'schematic', false);
        const wire = await api.sch_PrimitiveWire.create(vertices.flatMap(p => [p.x, p.y]), netName);
        if (!wire)
            throw new DomainError('CREATE_FAILED', 'SDK 未返回已创建导线；先回读再决定是否重试');
        return { primitiveId: wire.getState_PrimitiveId(), netName, vertices, coordinateUnit: '10mil', verification: '需回读网表与 DRC；不保证自动避障' };
    }
    async function autoLayout(raw: unknown) {
        requireWrite();
        const input = object(raw);
        await focus(input, 'pcb', false);
        if (typeof api.pcb_Document.autoLayout !== 'function')
            throw new DomainError('UNSUPPORTED', '当前客户端不支持自动布局');
        const result = await api.pcb_Document.autoLayout();
        await focus(input, 'pcb', false);
        return { status: 'returned', result, saved: false, verification: '回读器件位置与 DRC' };
    }
    async function autoRoute(raw: unknown) {
        requireWrite();
        const input = object(raw), nets = input.nets === undefined ? undefined : list(input.nets, 'nets', 1000).map(n => text(n, 'net'));
        await focus(input, 'pcb', false);
        if (typeof api.pcb_Document.autoRouting !== 'function')
            throw new DomainError('UNSUPPORTED', '当前客户端不支持自动布线');
        const result = await api.pcb_Document.autoRouting(nets ? { RoutingNets: nets } : undefined);
        await focus(input, 'pcb', false);
        return { status: 'returned', result, saved: false, verification: '检查 failedNets 与 DRC' };
    }
    async function saveDocument(raw: unknown) {
        requireWrite();
        const input = object(raw), { document } = await focus(input, undefined, false);
        const saved = document.documentType === 1 ? await api.sch_Document.save() : document.documentType === 3 ? await api.pcb_Document.save() : false;
        if (!saved)
            throw new DomainError('SAVE_FAILED', '文档未确认保存成功');
        return { saved: true, documentUuid: document.uuid };
    }
    async function exportManufacturing(raw: unknown) {
        const input = object(raw), formats = list(input.formats, 'formats', 3).map(v => text(v, 'format'));
        if (new Set(formats).size !== formats.length || formats.some(f => !['gerber', 'bom', 'pickAndPlace'].includes(f)))
            throw new DomainError('BAD_INPUT', '格式仅支持 gerber / bom / pickAndPlace，不能重复');
        const delivery = input.delivery ?? 'base64', prefix = input.prefix ?? 'Board';
        if (!['base64', 'dialog', 'filesystem'].includes(delivery as string))
            throw new DomainError('BAD_INPUT', '未知交付方式');
        if (typeof prefix !== 'string' || !/^[A-Za-z0-9_-]{1,48}$/.test(prefix))
            throw new DomainError('BAD_INPUT', '文件名前缀无效');
        let directory = '';
        if (delivery === 'filesystem') {
            directory = text(input.outputDirectory, 'outputDirectory');
            if (!/^(?:\/|[A-Za-z]:[\\/]|file:\/\/\/)/.test(directory) || directory.includes('\0') || /(?:^|[\\/])\.\.(?:[\\/]|$)/.test(directory))
                throw new DomainError('BAD_INPUT', '需要明确的绝对输出目录');
        }
        await focus(input, 'pcb');
        const files: Array<Record<string, unknown>> = [];
        try {
            for (const format of formats) {
                await focus(input, 'pcb');
                const name = `${prefix}_${format}.${format === 'gerber' ? 'zip' : 'csv'}`;
                const file = format === 'gerber' ? await api.pcb_ManufactureData.getGerberFile(prefix) : format === 'bom' ? await api.pcb_ManufactureData.getBomFile(prefix, 'csv') : await api.pcb_ManufactureData.getPickAndPlaceFile(prefix, 'csv');
                if (!file || file.size <= 0)
                    throw new Error('没有生成非空文件：' + format);
                if (file.size > 10 * 1024 * 1024)
                    throw new Error('本版每个导出文件上限 10MiB');
                const record: Record<string, unknown> = { format, name, bytes: file.size };
                if (delivery === 'base64') {
                    const bytes = new Uint8Array(await file.arrayBuffer());
                    if (bytes.length !== file.size)
                        throw new Error('文件字节数不一致');
                    record.base64 = base64(bytes);
                    record.status = 'generated';
                }
                else if (delivery === 'dialog') {
                    await api.sys_FileSystem.saveFile(file, name);
                    record.status = 'download_requested';
                }
                else {
                    const path = directory.replace(/[\\/]$/, '') + '/' + name;
                    const saved = await api.sys_FileSystem.saveFileToFileSystem(path, file, name, false);
                    if (!saved)
                        throw new Error('客户端未确认写入成功：' + path);
                    record.path = path;
                    record.status = 'saved_unverified';
                    files.push(record);
                    const actual = await api.sys_FileSystem.readFileFromFileSystem(path);
                    if (!actual || actual.size !== file.size)
                        throw new Error('已写入文件未通过大小回读检查：' + path);
                    const expectedBytes = new Uint8Array(await file.arrayBuffer()), actualBytes = new Uint8Array(await actual.arrayBuffer());
                    if (expectedBytes.length !== actualBytes.length || expectedBytes.some((byte, i) => byte !== actualBytes[i]))
                        throw new Error('已写入文件字节回读不一致：' + path);
                    record.status = 'saved';
                    record.byteVerified = true;
                    continue;
                }
                files.push(record);
            }
            return { files, delivery, verification: 'Gerber 层/钻孔及坐标需宿主回读与预览；不自动保存工程或下单' };
        }
        catch (error) {
            throw new DomainError('EXPORT_FAILED', String(error), files);
        }
    }
    return { getCapabilities, inspectProject, searchDevices, listComponents, getPins, getNetlist, checkDrc, placeSchematicComponents, connectPins, placePcbComponents, autoLayout, autoRoute, saveDocument, exportManufacturing };
}
