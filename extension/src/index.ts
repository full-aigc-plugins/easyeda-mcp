import config from '../extension.json' with { type: 'json' };
import { createController } from './controller';
import { NAMESPACE, operations, RPC_TOPIC } from './operations';
import { DomainError, object, text } from './validation';
const PLUGIN_TAG = '[EasyEDA MCP]';
const policy = { writeEnabled: false };
const controller = createController(eda, policy);
let registered = false;
/** 原生调用和内部面板共用确定性接口，不接受任意脚本。 */
export async function dispatch(name: string, input: unknown = {}) {
    try {
        const operation = operations.find(item => item.name === name);
        if (!operation)
            throw new DomainError('BAD_INPUT', '未知领域接口：' + name);
        return { ok: true, data: await controller[operation.name](input) };
    }
    catch (error) {
        console.error(PLUGIN_TAG, name, error);
        return { ok: false, error: { code: error instanceof DomainError ? error.code : 'OPERATION_FAILED',
                message: error instanceof Error ? error.message : String(error),
                ...(error instanceof DomainError && error.partial !== undefined ? { partial: error.partial } : {}) } };
    }
}
/** 激活时仅注册接口与私有消息服务，不打开/保存/修改工程。 */
export function activate(_status?: 'onStartupFinished', _arg?: string): void {
    if (registered)
        return;
    try {
        if (typeof eda.sys_ExternalApi?.register !== 'function')
            throw new Error('当前客户端不支持 sys_ExternalApi.register，请使用受支持的专业版');
        for (const operation of operations) {
            eda.sys_ExternalApi.register(NAMESPACE, operation.name, (input: unknown = {}) => dispatch(operation.name, input), {
                title: operation.title,
                description: operation.fields + (operation.write ? '；需要先由用户开启工程修改。超时后先回读，不重放。' : ''),
                params: [{ name: 'request', type: 'object', description: operation.fields, required: !['getCapabilities', 'inspectProject'].includes(operation.name) }],
                returns: { type: 'Promise<{ok:boolean,data?:unknown,error?:{code,message,partial?}}>', description: '检查 ok；返回结果不代表电气或制造验证完成' },
                example: `await external.${NAMESPACE}.${operation.name}(${['getCapabilities', 'inspectProject'].includes(operation.name) ? '{}' : '{projectUuid:"实际工程UUID",documentUuid:"实际文档UUID"}'})`,
            });
        }
        eda.sys_MessageBus.rpcService(RPC_TOPIC, async (raw: unknown) => {
            try {
                const request = object(raw), action = text(request.action, 'action');
                if (action === 'enableWrites') {
                    await enableWrites();
                    return { ok: true, data: await controller.getCapabilities({}) };
                }
                if (action === 'disableWrites') {
                    disableWrites();
                    return { ok: true, data: await controller.getCapabilities({}) };
                }
                return await dispatch(action, request.input);
            }
            catch (error) {
                return { ok: false, error: { code: 'BAD_INPUT', message: String(error) } };
            }
        });
        registered = true;
    }
    catch (error) {
        console.error(PLUGIN_TAG, '激活失败', error);
    }
}
export async function openPanel(): Promise<void> {
    activate();
    try {
        if (!registered)
            throw new Error('领域接口注册失败，请检查客户端版本与扩展权限');
        if (!await eda.sys_IFrame.openIFrame('/iframe/index.html', 980, 780, 'easyeda-mcp-panel'))
            throw new Error('客户端没有打开操作面板');
    }
    catch (error) {
        console.error(PLUGIN_TAG, '打开面板失败', error);
        eda.sys_Dialog.showInformationMessage(String(error), 'EasyEDA MCP');
    }
}
/** 开启仅由 EDA 用户确认，外部 API 参数不能改变该开关。 */
export function enableWrites(): Promise<void> {
    return new Promise(resolve => {
        eda.sys_Dialog.showConfirmationMessage('允许本次扩展会话创建器件、连线、布局布线及显式保存。操作仍须由你或已授权的 AI 请求；不会自动执行。', 'EasyEDA MCP', '开启工程修改', '保持只读', enabled => { policy.writeEnabled = enabled; resolve(); });
    });
}
export function disableWrites(): void { policy.writeEnabled = false; }
/** 原生接口调用时可查询版本；不会探测或发送外部网络。 */
export function version(): string { return config.version; }
