import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, mkdir, readFile, rm, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import JSZip from 'jszip';
import {packageExtension} from '../build/utils.ts';

test('全新检出未创建 build/dist 时仍能生成完整安装包', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'easyeda-package-'));
  try {
    await mkdir(path.join(root, 'dist'));
    await writeFile(path.join(root, 'extension.json'), '{"name":"test-extension"}');
    await writeFile(path.join(root, 'dist/index.js'), 'var extension = {};');
    await writeFile(path.join(root, '.edaignore'), '/.edaignore\n/build/\n');
    const target = path.join(root, 'build/dist/test.eext');
    await packageExtension(root, target);
    const archive = await JSZip.loadAsync(await readFile(target), {checkCRC32: true});
    assert.equal(await archive.file('dist/index.js').async('string'), 'var extension = {};');
    assert.equal(JSON.parse(await archive.file('extension.json').async('string')).name, 'test-extension');
    assert.equal(archive.file('.edaignore'), null);
  } finally {
    await rm(root, {recursive: true, force: true});
  }
});
