// zip を読む・書く（player/js/zip.js）
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readZip, makeZip, crc32, ZipError } from '../../player/js/zip.js';

const enc = new TextEncoder();

test('crc32: よく知られた値', () => {
  assert.equal(crc32(enc.encode('123456789')), 0xcbf43926);
  assert.equal(crc32(new Uint8Array(0)), 0);
});

test('makeZip → readZip: 中身・パス（UTF-8）・大きさが戻る', async () => {
  const pic = new Uint8Array(70000).map((_, i) => (i * 7) & 255);
  const zip = await makeZip([
    { path: 'my-story/work.json', data: '{"title":"灯台"}' },
    { path: 'my-story/pictures/01.jpg', data: new Blob([pic]) },
    { path: 'my-story/台本.md', data: '# 灯台\n' },
  ]);
  const entries = await readZip(zip);
  assert.deepEqual(entries.map((e) => [e.path, e.size, e.method]), [
    ['my-story/work.json', enc.encode('{"title":"灯台"}').length, 0],
    ['my-story/pictures/01.jpg', 70000, 0],
    ['my-story/台本.md', enc.encode('# 灯台\n').length, 0],
  ]);
  const f = await entries[1].file();
  assert.equal(f.name, '01.jpg');
  assert.deepEqual(new Uint8Array(await f.arrayBuffer()), pic);
  assert.equal(await (await entries[2].file()).text(), '# 灯台\n');
});

/** テスト用: deflate で縮めた1件の zip（ほかの道具が作る zip の形）。フォルダの行も1つ入れる */
async function deflatedZip(path, text) {
  const data = enc.encode(text);
  const packed = new Uint8Array(await new Response(new Blob([data]).stream().pipeThrough(new CompressionStream('deflate-raw'))).arrayBuffer());
  const name = enc.encode(path);
  const dir = enc.encode('folder/');
  const local = new DataView(new ArrayBuffer(30));
  local.setUint32(0, 0x04034b50, true); local.setUint16(4, 20, true); local.setUint16(8, 8, true);
  local.setUint32(14, crc32(data), true); local.setUint32(18, packed.length, true); local.setUint32(22, data.length, true);
  local.setUint16(26, name.length, true);
  const cdir = new DataView(new ArrayBuffer(46));
  cdir.setUint32(0, 0x02014b50, true); cdir.setUint16(28, dir.length, true); cdir.setUint32(42, 0, true);
  const c = new DataView(new ArrayBuffer(46));
  c.setUint32(0, 0x02014b50, true); c.setUint16(10, 8, true); c.setUint32(16, crc32(data), true);
  c.setUint32(20, packed.length, true); c.setUint32(24, data.length, true); c.setUint16(28, name.length, true); c.setUint32(42, 0, true);
  const cdSize = 46 + dir.length + 46 + name.length;
  const e = new DataView(new ArrayBuffer(22));
  e.setUint32(0, 0x06054b50, true); e.setUint16(8, 2, true); e.setUint16(10, 2, true);
  e.setUint32(12, cdSize, true); e.setUint32(16, 30 + name.length + packed.length, true);
  return new Blob([local, name, packed, cdir, dir, c, name, e]);
}

test('readZip: deflate の中身をほどく・フォルダの行は入れない', async () => {
  const text = 'line\n'.repeat(5000);
  const entries = await readZip(await deflatedZip('folder/script.md', text));
  assert.deepEqual(entries.map((e) => [e.path, e.method]), [['folder/script.md', 8]]);
  assert.ok(entries[0].packed < entries[0].size);
  assert.equal(await (await entries[0].file()).text(), text);
});

test('readZip: zip でないもの・切れた zip は ZipError', async () => {
  await assert.rejects(readZip(new Blob(['not a zip at all'])), ZipError);
  const zip = await makeZip([{ path: 'a.txt', data: 'hello' }]);
  await assert.rejects(readZip(zip.slice(10)), ZipError);
});

test('makeZip: zip の外を指すパスは書かない', async () => {
  for (const bad of ['../x', '/abs', 'a//b', '']) await assert.rejects(makeZip([{ path: bad, data: 'x' }]), ZipError, bad);
});

/** テスト用: 名前のバイト列と汎用ビットフラグを指定した、圧縮なしの zip（ほかの道具が書く名前の形） */
function namedZip(items) {
  const parts = [];
  const central = [];
  let offset = 0;
  for (const { name, flags, text } of items) {
    const data = enc.encode(text);
    const local = new DataView(new ArrayBuffer(30));
    local.setUint32(0, 0x04034b50, true); local.setUint16(6, flags, true);
    local.setUint32(14, crc32(data), true); local.setUint32(18, data.length, true); local.setUint32(22, data.length, true);
    local.setUint16(26, name.length, true);
    const c = new DataView(new ArrayBuffer(46));
    c.setUint32(0, 0x02014b50, true); c.setUint16(8, flags, true); c.setUint32(16, crc32(data), true);
    c.setUint32(20, data.length, true); c.setUint32(24, data.length, true); c.setUint16(28, name.length, true); c.setUint32(42, offset, true);
    parts.push(local, name, data);
    central.push(c, name);
    offset += 30 + name.length + data.length;
  }
  const cdSize = central.reduce((a, b) => a + b.byteLength, 0);
  const e = new DataView(new ArrayBuffer(22));
  e.setUint32(0, 0x06054b50, true); e.setUint16(8, items.length, true); e.setUint16(10, items.length, true);
  e.setUint32(12, cdSize, true); e.setUint32(16, offset, true);
  return new Blob([...parts, ...central, e]);
}

// 「わたしの話/絵/はじまり.jpg」「わたしの話/表紙.jpg」を Shift_JIS で（「表」の2バイト目は '\' と同じ 0x5C）
const SJIS_PIC = new Uint8Array([130, 237, 130, 189, 130, 181, 130, 204, 152, 98, 47, 138, 71, 47, 130, 205, 130, 182, 130, 220, 130, 232, 46, 106, 112, 103]);
const SJIS_COVER = new Uint8Array([130, 237, 130, 189, 130, 181, 130, 204, 152, 98, 47, 0x95, 0x5c, 0x8e, 0x86, 46, 106, 112, 103]);

test('readZip: UTF-8 の印付きの日本語のファイル名は UTF-8 で読む', async () => {
  const entries = await readZip(namedZip([{ name: enc.encode('わたしの話/絵/はじまり.jpg'), flags: 0x0800, text: 'a' }]));
  assert.deepEqual(entries.map((x) => x.path), ['わたしの話/絵/はじまり.jpg']);
  assert.equal((await entries[0].file()).name, 'はじまり.jpg');
});

test('readZip: 印の無い日本語のファイル名は Shift_JIS で読む（2バイト目の 0x5C をフォルダの区切りにしない）', async () => {
  const entries = await readZip(namedZip([
    { name: SJIS_PIC, flags: 0, text: 'a' },
    { name: SJIS_COVER, flags: 0, text: 'b' },
    { name: enc.encode('わたしの話/work.json'), flags: 0, text: '{}' },
  ]));
  assert.deepEqual(entries.map((x) => x.path), ['わたしの話/絵/はじまり.jpg', 'わたしの話/表紙.jpg', 'わたしの話/work.json']);
  assert.equal((await entries[1].file()).name, '表紙.jpg');
  assert.equal(await (await entries[1].file()).text(), 'b');
});

test('readZip: 印が無くても、正しい UTF-8 の名前はそのまま（Mac の「圧縮」の書き方）', async () => {
  const entries = await readZip(namedZip([{ name: enc.encode('わたしの話/絵/はじまり.jpg'), flags: 0, text: 'a' }]));
  assert.deepEqual(entries.map((x) => x.path), ['わたしの話/絵/はじまり.jpg']);
});
