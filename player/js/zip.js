// zip を読む・書く（docs/work-format.md §1 Zip）。ライブラリなし。DOM に触らない（node --test で守る）。
// 読む: 目次（中央ディレクトリ）を読み、中身は要るときに1つずつほどく。圧縮なしは切り出すだけ、deflate は DecompressionStream。
//       iPad はフォルダを選べないので、作品を zip にすれば開ける。
// 書く: 圧縮なし（CRC32 だけ）。写真・動画はもう圧縮されているので、縮めても小さくならない。画面で使うのは段4（写真を添えるとき）。
// zip64（4GB を超える zip）は読まない（理由を出して止める）。

const EOCD = 0x06054b50;
const CENTRAL = 0x02014b50;
const LOCAL = 0x04034b50;
const UTF8 = 0x0800;

export class ZipError extends Error {}

const u16 = (v, o) => v.getUint16(o, true);
const u32 = (v, o) => v.getUint32(o, true);

async function bytesOf(blob, start, end) {
  return new DataView(await blob.slice(start, end).arrayBuffer());
}

/** DOS の日時 → ミリ秒（壊れていれば 0） */
function dosTime(date, time) {
  const y = 1980 + (date >> 9);
  const t = Date.UTC(y, ((date >> 5) & 15) - 1, date & 31, time >> 11, (time >> 5) & 63, (time & 31) * 2);
  return Number.isFinite(t) && t > 0 ? t : 0;
}

/** zip の目次を読む → [{ path, size, packed, method, file() }]。file() はその中身の File（要るときにほどく）。
 *  フォルダの行は入れない。読めない zip は ZipError */
export async function readZip(blob) {
  const tail = Math.min(blob.size, 22 + 0xffff);
  const end = await bytesOf(blob, blob.size - tail, blob.size);
  let at = -1;
  for (let i = end.byteLength - 22; i >= 0; i--) if (u32(end, i) === EOCD) { at = i; break; }
  if (at < 0) throw new ZipError('not a zip file');
  const count = u16(end, at + 10);
  const cdSize = u32(end, at + 12);
  const cdOffset = u32(end, at + 16);
  if (count === 0xffff || cdSize === 0xffffffff || cdOffset === 0xffffffff) throw new ZipError('zip64 is not read here (a zip over 4 GB)');
  if (cdOffset + cdSize > blob.size) throw new ZipError('the zip is cut short');
  const cd = await bytesOf(blob, cdOffset, cdOffset + cdSize);
  const dec = new TextDecoder('utf-8');
  const out = [];
  let p = 0;
  for (let k = 0; k < count; k++) {
    if (p + 46 > cd.byteLength || u32(cd, p) !== CENTRAL) throw new ZipError('the table of contents is broken');
    const method = u16(cd, p + 10);
    const time = u16(cd, p + 12);
    const date = u16(cd, p + 14);
    const packed = u32(cd, p + 20);
    const size = u32(cd, p + 24);
    const nameLen = u16(cd, p + 28);
    const extraLen = u16(cd, p + 30);
    const commentLen = u16(cd, p + 32);
    const local = u32(cd, p + 42);
    const name = dec.decode(new Uint8Array(cd.buffer, cd.byteOffset + p + 46, nameLen)).replace(/\\/g, '/');
    p += 46 + nameLen + extraLen + commentLen;
    if (name.endsWith('/')) continue;
    if (packed === 0xffffffff || size === 0xffffffff || local === 0xffffffff) throw new ZipError('zip64 is not read here (a zip over 4 GB)');
    if (method !== 0 && method !== 8) throw new ZipError(`${name}: compressed in a way this player cannot open (method ${method})`);
    const base = name.split('/').pop();
    const lastModified = dosTime(date, time);
    out.push({
      path: name, size, packed, method,
      async file() {
        const h = await bytesOf(blob, local, local + 30);
        if (u32(h, 0) !== LOCAL) throw new ZipError(`${name}: the file inside is broken`);
        const start = local + 30 + u16(h, 26) + u16(h, 28);
        const data = blob.slice(start, start + packed);
        if (method === 0) return new File([data], base, { lastModified });
        const plain = await new Response(data.stream().pipeThrough(new DecompressionStream('deflate-raw'))).blob();
        if (plain.size !== size) throw new ZipError(`${name}: unpacked to the wrong size`);
        return new File([plain], base, { lastModified });
      },
    });
  }
  return out;
}

// ---------- 書く（圧縮なし） ----------

let TABLE = null;
function crcTable() {
  if (TABLE) return TABLE;
  TABLE = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    TABLE[n] = c >>> 0;
  }
  return TABLE;
}

/** CRC-32（zip と同じ） */
export function crc32(bytes, crc = 0) {
  const t = crcTable();
  let c = (crc ^ 0xffffffff) >>> 0;
  for (let i = 0; i < bytes.length; i++) c = t[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function dosOf(ms) {
  const d = new Date(ms || Date.UTC(1980, 0, 1));
  const y = Math.max(1980, d.getUTCFullYear());
  return {
    date: ((y - 1980) << 9) | ((d.getUTCMonth() + 1) << 5) | d.getUTCDate(),
    time: (d.getUTCHours() << 11) | (d.getUTCMinutes() << 5) | (d.getUTCSeconds() >> 1),
  };
}

/** [{ path, data（Blob・Uint8Array・文字）, lastModified? }] → 圧縮なしの zip の Blob。パスは '/' 区切り・UTF-8 */
export async function makeZip(items) {
  const enc = new TextEncoder();
  const parts = [];
  const central = [];
  let offset = 0;
  for (const it of items) {
    const path = String(it.path).replace(/\\/g, '/');
    if (!path || path.startsWith('/') || path.split('/').some((s) => s === '..' || s === '')) throw new ZipError(`not a path inside a zip: ${path}`);
    const name = enc.encode(path);
    const data = it.data instanceof Blob ? new Uint8Array(await it.data.arrayBuffer())
      : typeof it.data === 'string' ? enc.encode(it.data) : new Uint8Array(it.data);
    if (data.length >= 0xffffffff || offset >= 0xffffffff) throw new ZipError('over 4 GB: zip64 is not written here');
    const crc = crc32(data);
    const { date, time } = dosOf(it.lastModified);
    const head = new DataView(new ArrayBuffer(30));
    head.setUint32(0, LOCAL, true); head.setUint16(4, 10, true); head.setUint16(6, UTF8, true); head.setUint16(8, 0, true);
    head.setUint16(10, time, true); head.setUint16(12, date, true); head.setUint32(14, crc, true);
    head.setUint32(18, data.length, true); head.setUint32(22, data.length, true); head.setUint16(26, name.length, true); head.setUint16(28, 0, true);
    const c = new DataView(new ArrayBuffer(46));
    c.setUint32(0, CENTRAL, true); c.setUint16(4, 20, true); c.setUint16(6, 10, true); c.setUint16(8, UTF8, true); c.setUint16(10, 0, true);
    c.setUint16(12, time, true); c.setUint16(14, date, true); c.setUint32(16, crc, true);
    c.setUint32(20, data.length, true); c.setUint32(24, data.length, true); c.setUint16(28, name.length, true);
    c.setUint32(42, offset, true);
    parts.push(head, name, data);
    central.push(c, name);
    offset += 30 + name.length + data.length;
  }
  const cdSize = central.reduce((a, b) => a + b.byteLength, 0);
  const e = new DataView(new ArrayBuffer(22));
  e.setUint32(0, EOCD, true); e.setUint16(8, items.length, true); e.setUint16(10, items.length, true);
  e.setUint32(12, cdSize, true); e.setUint32(16, offset, true);
  return new Blob([...parts, ...central, e], { type: 'application/zip' });
}
