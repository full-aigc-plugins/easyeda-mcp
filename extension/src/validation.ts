export class DomainError extends Error {
    constructor(public code: string, message: string, public partial?: unknown) { super(message); }
}
/** 校验外部 JSON；运行时不依赖 Node 或 DOM。 */
export function object(value: unknown = {}): Record<string, unknown> {
    if (!value || typeof value !== 'object' || Array.isArray(value))
        throw new DomainError('BAD_INPUT', '参数必须是 JSON 对象');
    return value as Record<string, unknown>;
}
export function text(value: unknown, name: string): string {
    if (typeof value !== 'string' || !value.trim() || value.length > 2048)
        throw new DomainError('BAD_INPUT', name + ' 必须是非空字符串，最多 2048 字符');
    return value;
}
export function number(value: unknown, name: string): number {
    if (typeof value !== 'number' || !Number.isFinite(value))
        throw new DomainError('BAD_INPUT', name + ' 必须是有限数字');
    return value;
}
export function list(value: unknown, name: string, max = 100): unknown[] {
    if (!Array.isArray(value) || value.length < 1 || value.length > max)
        throw new DomainError('BAD_INPUT', name + ` 需要 1~${max} 项`);
    return value;
}
export function page(input: Record<string, unknown>, max = 200) {
    const offset = input.offset ?? 0, limit = input.limit ?? Math.min(50, max);
    if (!Number.isInteger(offset) || !Number.isInteger(limit) || (offset as number) < 0 || (limit as number) < 1 || (limit as number) > max)
        throw new DomainError('BAD_INPUT', '分页范围无效');
    return { offset: offset as number, limit: limit as number };
}
/** 不使用沙箱未保证存在的 btoa；编码 SDK File 的真实字节。 */
export function base64(bytes: Uint8Array): string {
    const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/', result: string[] = [];
    for (let start = 0; start < bytes.length; start += 12288) {
        let chunk = '';
        for (let i = start; i < Math.min(start + 12288, bytes.length); i += 3) {
            const a = bytes[i], b = bytes[i + 1] ?? 0, c = bytes[i + 2] ?? 0;
            chunk += alphabet[a >> 2] + alphabet[((a & 3) << 4) | (b >> 4)]
                + (i + 1 < bytes.length ? alphabet[((b & 15) << 2) | (c >> 6)] : '=')
                + (i + 2 < bytes.length ? alphabet[c & 63] : '=');
        }
        result.push(chunk);
    }
    return result.join('');
}
