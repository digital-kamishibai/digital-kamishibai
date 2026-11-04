import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createScanner, finalize } from '../../player/js/mp4fix.js';

// ---------- 小さな断片 MP4 を組み立てる（Chrome の MediaRecorder と同じ書き方: tfhd 0x020020・trun 0x305／0x301） ----------

const enc = new TextEncoder();
const cat = (...a) => { const out = new Uint8Array(a.reduce((n, x) => n + x.length, 0)); let o = 0; for (const x of a) { out.set(x, o); o += x.length; } return out; };
const w = (...ns) => { const b = new Uint8Array(ns.length * 4); const dv = new DataView(b.buffer); ns.forEach((n, i) => dv.setUint32(i * 4, n >>> 0)); return b; };
const box = (t, ...p) => { const body = cat(...p); return cat(w(body.length + 8), enc.encode(t), body); };
const full = (t, vf, ...p) => box(t, w(vf), ...p);

const VIDEO = 1, AUDIO = 2;
function initSegment() {
  const trak = (id, handler, scale) => box('trak',
    full('tkhd', 3, w(0, 0, id, 0, 0), new Uint8Array(60)),
    box('mdia',
      full('mdhd', 0, w(0, 0, scale, 0), w(0)),
      full('hdlr', 0, w(0), enc.encode(handler), w(0, 0, 0), new Uint8Array(1)),
      box('minf',
        handler === 'vide' ? full('vmhd', 1, new Uint8Array(8)) : full('smhd', 0, w(0)),
        box('dinf', full('dref', 0, w(1), full('url ', 1))),
        box('stbl', full('stsd', 0, w(1), box(handler === 'vide' ? 'avc1' : 'mp4a', new Uint8Array(16))),
          full('stts', 0, w(0)), full('stsc', 0, w(0)), full('stsz', 0, w(0, 0)), full('stco', 0, w(0))))));
  return cat(
    box('ftyp', enc.encode('isom'), w(0)),
    box('moov',
      full('mvhd', 0, w(0, 0, 1000, 0), new Uint8Array(80)),
      trak(VIDEO, 'vide', 30000), trak(AUDIO, 'soun', 44100),
      box('mvex', full('trex', 0, w(AUDIO, 1, 0, 0, 0)), full('trex', 0, w(VIDEO, 1, 0, 0, 0)))));
}

/** 断片1つ: 映像 n コマ（先頭だけキーフレーム）＋音 m 個。中身は「どのトラックの何番目か」が分かるバイトで埋める */
function fragment(seq, offset, vids, auds) {
  const NONSYNC = 0x01010000, SYNC = 0x02000000;
  const vRun = (dataOff) => full('trun', (1 << 24) | 0x305, w(vids.length, dataOff, SYNC), ...vids.map((v) => w(1001, v.size)));
  const aRun = (dataOff) => full('trun', (1 << 24) | 0x301, w(auds.length, dataOff), ...auds.map((a) => w(1024, a.size)));
  const build = (vOff, aOff) => box('moof', full('mfhd', 0, w(seq)),
    box('traf', full('tfhd', 0x020020, w(VIDEO, NONSYNC)), full('tfdt', 1 << 24, w(0, 0)), vRun(vOff)),
    box('traf', full('tfhd', 0x020020, w(AUDIO, 0x02000000)), full('tfdt', 1 << 24, w(0, 0)), aRun(aOff)));
  const moofLen = build(0, 0).length;
  const vBytes = cat(...vids.map((v) => new Uint8Array(v.size).fill(v.mark)));
  const aBytes = cat(...auds.map((a) => new Uint8Array(a.size).fill(a.mark)));
  const moof = build(moofLen + 8, moofLen + 8 + vBytes.length); // data_offset は moof の頭から
  return cat(moof, box('mdat', vBytes, aBytes));
}

function recording() {
  const init = initSegment();
  const f1 = fragment(1, init.length, [{ size: 50, mark: 11 }, { size: 20, mark: 12 }, { size: 21, mark: 13 }], [{ size: 9, mark: 21 }, { size: 8, mark: 22 }]);
  const f2 = fragment(2, init.length + f1.length, [{ size: 40, mark: 14 }, { size: 22, mark: 15 }], [{ size: 7, mark: 23 }]);
  return cat(init, f1, f2);
}

// ---------- 直した結果を読む ----------

const u32 = (b, o) => ((b[o] << 24) | (b[o + 1] << 16) | (b[o + 2] << 8) | b[o + 3]) >>> 0;
const typ = (b, o) => String.fromCharCode(...b.subarray(o + 4, o + 8));
function top(b) { const out = []; for (let o = 0; o < b.length;) { const s = u32(b, o); out.push([typ(b, o), o, s]); o += s; } return out; }
function find(b, start, end, path) {
  for (let o = start; o < end;) {
    const s = u32(b, o); const t = typ(b, o);
    if (t === path[0]) return path.length === 1 ? { o, s } : find(b, o + 8, o + s, path.slice(1));
    o += s;
  }
  return null;
}
function apply(file, fix) {
  const out = new Uint8Array(fix.position + fix.append.length);
  out.set(file);
  for (const p of fix.patches) out.set(p.data, p.position);
  out.set(fix.append, fix.position);
  return out;
}
function scan(file, step) {
  const sc = createScanner();
  for (let o = 0; o < file.length; o += step) sc.push(file.subarray(o, o + step));
  return sc.result();
}
/** 新しい moov の中のトラックを読む（trak の順） */
function tracksOf(b, moov) {
  const out = [];
  for (let o = moov.o + 8; o < moov.o + moov.s;) {
    const s = u32(b, o);
    if (typ(b, o) === 'trak') {
      const stbl = find(b, o + 8, o + s, ['mdia', 'minf', 'stbl']);
      const at = (name) => find(b, stbl.o + 8, stbl.o + stbl.s, [name]);
      const stsz = at('stsz'); const stco = at('stco'); const stss = at('stss'); const stts = at('stts');
      const n = u32(b, stsz.o + 16);
      out.push({
        id: u32(b, find(b, o + 8, o + s, ['tkhd']).o + 20),
        tkhdDur: u32(b, find(b, o + 8, o + s, ['tkhd']).o + 28),
        mdhdDur: u32(b, find(b, o + 8, o + s, ['mdia', 'mdhd']).o + 24),
        sizes: Array.from({ length: n }, (_, i) => u32(b, stsz.o + 20 + i * 4)),
        chunks: Array.from({ length: u32(b, stco.o + 12) }, (_, i) => u32(b, stco.o + 16 + i * 4)),
        syncs: stss ? Array.from({ length: u32(b, stss.o + 12) }, (_, i) => u32(b, stss.o + 16 + i * 4)) : null,
        stts: Array.from({ length: u32(b, stts.o + 12) * 2 }, (_, i) => u32(b, stts.o + 16 + i * 4)),
        hasStsd: !!at('stsd'),
      });
    }
    o += s;
  }
  return out;
}

test('断片に分けた MP4 を、索引を末尾に持つふつうの MP4 に直す（中身の mdat は動かさない）', () => {
  const file = recording();
  const fix = finalize(scan(file, 1 << 20));
  assert.ok(fix);
  const out = apply(file, fix);
  assert.deepEqual(top(out).map((x) => x[0]), ['ftyp', 'free', 'free', 'mdat', 'free', 'mdat', 'moov']);
  // もとの mdat はそのままの位置・中身
  for (const [t, o, s] of top(file)) if (t === 'mdat') assert.deepEqual(out.subarray(o, o + s), file.subarray(o, o + s));
});

test('長さ: mvhd・tkhd・mdhd にコマの長さの合計が入る（Windows のメディアプレイヤーがシークバーを出す）', () => {
  const file = recording();
  const fix = finalize(scan(file, 1 << 20));
  const out = apply(file, fix);
  const moov = find(out, fix.position, out.length, ['moov']);
  const mvhd = find(out, moov.o + 8, moov.o + moov.s, ['mvhd']);
  assert.equal(u32(out, mvhd.o + 24), Math.round(5 * 1001 / 30));           // 映像のほうが長い（ms）
  const [v, a] = tracksOf(out, moov);
  assert.equal(v.mdhdDur, 5 * 1001);
  assert.equal(a.mdhdDur, 3 * 1024);
  assert.equal(v.tkhdDur, Math.round(5 * 1001 / 30));
  assert.equal(a.tkhdDur, Math.round(3 * 1024 * 1000 / 44100));
  assert.ok(Math.abs(fix.duration - 5 * 1001 / 30000) < 0.001);
});

test('索引: 大きさ・置き場所・キーフレームが、断片の表のとおり（置き場所は本当にそのコマの中身を指す）', () => {
  const file = recording();
  const fix = finalize(scan(file, 1 << 20));
  const out = apply(file, fix);
  const [v, a] = tracksOf(out, find(out, fix.position, out.length, ['moov']));
  assert.equal(v.id, VIDEO);
  assert.deepEqual(v.sizes, [50, 20, 21, 40, 22]);
  assert.deepEqual(a.sizes, [9, 8, 7]);
  assert.deepEqual(v.chunks.map((o) => out[o]), [11, 14]);                    // 断片ごとの最初のコマ
  assert.deepEqual(a.chunks.map((o) => out[o]), [21, 23]);
  assert.equal(out[v.chunks[0] + 50], 12);                                   // 2コマ目は1コマ目のすぐ後ろ
  assert.deepEqual(v.syncs, [1, 4]);                                         // 断片の先頭だけキーフレーム
  assert.deepEqual(v.stts, [5, 1001]);
  assert.ok(v.hasStsd && a.hasStsd);                                         // 符号の設定（stsd）はもとのまま写す
});

test('書き込みの区切り方（どこで切れても）で結果は変わらない', () => {
  const file = recording();
  const a = finalize(scan(file, 1 << 20));
  for (const step of [1, 7, 8, 9, 16, 33, 100]) {
    const b = finalize(scan(file, step));
    assert.deepEqual(apply(file, b), apply(file, a), `step ${step}`);
  }
});

test('直せないもの（断片に分けていない・途中で切れた・MP4 でない）は何もしない', () => {
  const file = recording();
  assert.equal(finalize(scan(file.subarray(0, file.length - 5), 64)), null);  // 途中で切れた
  assert.equal(finalize(scan(initSegment(), 64)), null);                      // 断片が無い
  assert.equal(finalize(scan(new Uint8Array([0x1a, 0x45, 0xdf, 0xa3, 0, 0, 0, 0, 1, 2]), 64)), null); // WebM
  assert.equal(finalize(null), null);
});

test('書き換えは箱の名前4文字だけ（大きさを変えない＝中身の位置がずれない）', () => {
  const file = recording();
  const fix = finalize(scan(file, 1 << 20));
  assert.equal(fix.patches.length, 3); // もとの moov と moof 2つ
  for (const p of fix.patches) { assert.equal(p.data.length, 4); assert.equal(String.fromCharCode(...p.data), 'free'); }
  assert.equal(fix.position, file.length); // 足すのは末尾だけ
});
