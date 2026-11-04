// 録画の MP4 を「ふつうの MP4」に直す（録画と練習 G3 の続き。2026-10-24 の実機確認で見つけた）。
// DOM にも通信にも触らない純粋な関数だけを置く（node --test で守る）。
//
// ⚠️ Chrome の MediaRecorder は MP4 を**断片に分けた形（fragmented MP4）**で書く: 頭の moov に長さ 0 と空の索引、
//    そのあとに moof（その断片のコマの表）＋ mdat（中身）が並ぶ。ffprobe は断片を全部読んで長さを数えるが、
//    **Windows のメディアプレイヤーは頭の「長さ 0」を信じてシークバーを出さない**。
// 直し方（中身の mdat は動かさない＝1GB でもコピーしない）:
//   1. 書きながら、moov と moof だけを拾う（mdat の中身は読み飛ばす。createScanner）
//   2. 止めたときに、全部のコマの索引を持つ moov を作り、ファイルの末尾に足す（finalize の append）
//   3. もとの moov と moof は、同じ大きさのまま箱の名前を 'free'（読み飛ばされる箱）に書き換える（finalize の patches）
//   → 「ftyp・free…・mdat・free・mdat…・moov」の、ふつうの MP4（索引が末尾にある形）になる

const enc = new TextEncoder();
const u32 = (b, o) => ((b[o] << 24) | (b[o + 1] << 16) | (b[o + 2] << 8) | b[o + 3]) >>> 0;
const i32 = (b, o) => u32(b, o) | 0;
const u64 = (b, o) => u32(b, o) * 2 ** 32 + u32(b, o + 4);
const type = (b, o) => String.fromCharCode(b[o], b[o + 1], b[o + 2], b[o + 3]);

/** 箱の並び（b の start〜end）。{ type, start, head, size } */
function* boxes(b, start = 0, end = b.length) {
  let o = start;
  while (o + 8 <= end) {
    let size = u32(b, o);
    let head = 8;
    if (size === 1) { size = u64(b, o + 8); head = 16; }
    if (size === 0) size = end - o;
    if (size < head || o + size > end) return;
    yield { type: type(b, o + 4), start: o, head, size };
    o += size;
  }
}
const child = (b, box, name) => { for (const x of boxes(b, box.start + box.head, box.start + box.size)) if (x.type === name) return x; return null; };
const kids = (b, box) => [...boxes(b, box.start + box.head, box.start + box.size)];

// ---------- 1. 書きながら拾う ----------

/** 書き出すバイト列を順に push して、moov と moof（と mdat の位置）を拾う。mdat の中身は抱えない。
 *  戻り値の result(): { ftyp, moov: { offset, bytes }, moofs: [{ offset, bytes }], size } */
export function createScanner() {
  let pos = 0;            // これまでに push したバイト数（ファイルの中の位置）
  let head = new Uint8Array(0); // 箱の頭を読みかけ
  let box = null;         // いま読んでいる箱 { type, offset, size, keep: Uint8Array | null, got }
  let moov = null;
  const moofs = [];
  let ftyp = false;
  let broken = false;

  function push(chunk) {
    let c = chunk instanceof Uint8Array ? chunk : new Uint8Array(chunk);
    while (c.length && !broken) {
      if (!box) {
        // 箱の頭（8バイト。大きい箱は16バイト）を集める
        const need = head.length < 8 ? 8 : (u32(head, 0) === 1 ? 16 : 8);
        const take = Math.min(need - head.length, c.length);
        const h = new Uint8Array(head.length + take);
        h.set(head); h.set(c.subarray(0, take), head.length);
        head = h; c = c.subarray(take); pos += take;
        if (head.length < 8) continue;
        if (u32(head, 0) === 1 && head.length < 16) continue;
        const size = u32(head, 0) === 1 ? u64(head, 8) : u32(head, 0);
        const t = type(head, 4);
        if (size < head.length) { broken = true; return; } // 長さ 0（終わりまで）の箱は Chrome は書かない
        const keep = t === 'moov' || t === 'moof' ? new Uint8Array(size) : null;
        if (keep) keep.set(head);
        if (t === 'ftyp') ftyp = true;
        box = { type: t, offset: pos - head.length, size, keep, got: head.length };
        head = new Uint8Array(0);
      }
      const take = Math.min(box.size - box.got, c.length);
      if (box.keep) box.keep.set(c.subarray(0, take), box.got);
      box.got += take; c = c.subarray(take); pos += take;
      if (box.got === box.size) {
        if (box.type === 'moov') moov = { offset: box.offset, bytes: box.keep };
        if (box.type === 'moof') moofs.push({ offset: box.offset, bytes: box.keep });
        box = null;
      }
    }
  }

  return {
    push,
    result: () => ({ ftyp, moov, moofs, size: pos, complete: !box && !head.length && !broken }),
  };
}

// ---------- 2. 索引を作る ----------

/** 1本のトラックの全部のコマ（moof の表から）。{ id, durations, sizes, syncs, ctos, chunks:[{ offset, count }] } */
function samplesOf(scan) {
  const b = scan.moov.bytes;
  const moov = { start: 0, head: 8, size: b.length };
  const defaults = new Map(); // track_ID → trex の既定値
  const mvex = child(b, moov, 'mvex');
  if (mvex) {
    for (const x of kids(b, mvex)) {
      if (x.type !== 'trex') continue;
      const o = x.start + 12;
      defaults.set(u32(b, o), { duration: u32(b, o + 8), size: u32(b, o + 12), flags: u32(b, o + 16) });
    }
  }
  const tracks = new Map();
  for (const f of scan.moofs) {
    const m = f.bytes;
    const moof = { start: 0, head: 8, size: m.length };
    for (const traf of kids(m, moof)) {
      if (traf.type !== 'traf') continue;
      const tfhd = child(m, traf, 'tfhd');
      if (!tfhd) continue;
      const tf = u32(m, tfhd.start + 8) & 0xffffff;
      let o = tfhd.start + 12;
      const id = u32(m, o); o += 4;
      const d = defaults.get(id) || { duration: 0, size: 0, flags: 0 };
      let base = f.offset; // 既定は moof の頭（default-base-is-moof・Chrome の書き方）
      if (tf & 0x1) { base = u64(m, o); o += 8; }
      if (tf & 0x2) o += 4;
      let dDur = d.duration; if (tf & 0x8) { dDur = u32(m, o); o += 4; }
      let dSize = d.size; if (tf & 0x10) { dSize = u32(m, o); o += 4; }
      let dFlags = d.flags; if (tf & 0x20) { dFlags = u32(m, o); o += 4; }
      if (!tracks.has(id)) tracks.set(id, { id, durations: [], sizes: [], syncs: [], ctos: [], chunks: [] });
      const tr = tracks.get(id);
      for (const run of kids(m, traf)) {
        if (run.type !== 'trun') continue;
        const vf = u32(m, run.start + 8);
        const v = vf >>> 24;
        const rf = vf & 0xffffff;
        let p = run.start + 12;
        const n = u32(m, p); p += 4;
        let offset = base;
        if (rf & 0x1) { offset = base + i32(m, p); p += 4; }
        let first = null; if (rf & 0x4) { first = u32(m, p); p += 4; }
        tr.chunks.push({ offset, count: n });
        for (let i = 0; i < n; i++) {
          let dur = dDur; if (rf & 0x100) { dur = u32(m, p); p += 4; }
          let size = dSize; if (rf & 0x200) { size = u32(m, p); p += 4; }
          let flags = i === 0 && first != null ? first : dFlags; if (rf & 0x400) { flags = u32(m, p); p += 4; }
          let cto = 0; if (rf & 0x800) { cto = v === 0 ? u32(m, p) : i32(m, p); p += 4; }
          tr.durations.push(dur);
          tr.sizes.push(size);
          tr.syncs.push(!(flags & 0x10000)); // sample_is_non_sync_sample が立っていなければキーフレーム
          tr.ctos.push(cto);
        }
      }
    }
  }
  return tracks;
}

function box(name, ...parts) {
  const len = parts.reduce((a, p) => a + p.length, 8);
  const out = new Uint8Array(len);
  const dv = new DataView(out.buffer);
  dv.setUint32(0, len);
  out.set(enc.encode(name), 4);
  let o = 8;
  for (const p of parts) { out.set(p, o); o += p.length; }
  return out;
}
function words(...ns) {
  const out = new Uint8Array(ns.length * 4);
  const dv = new DataView(out.buffer);
  ns.forEach((n, i) => dv.setUint32(i * 4, n >>> 0));
  return out;
}
const full = (name, version, flags, ...parts) => box(name, words(((version & 0xff) << 24) | (flags & 0xffffff)), ...parts);

/** 連続する同じ値をまとめる（stts・ctts） */
function runs(values) {
  const out = [];
  for (const v of values) {
    const last = out[out.length - 1];
    if (last && last[1] === v) last[0] += 1; else out.push([1, v]);
  }
  return out;
}

function sampleTable(tr) {
  const parts = [];
  const stts = runs(tr.durations);
  parts.push(full('stts', 0, 0, words(stts.length, ...stts.flat())));
  if (tr.ctos.some((c) => c !== 0)) {
    const ctts = runs(tr.ctos);
    parts.push(full('ctts', tr.ctos.some((c) => c < 0) ? 1 : 0, 0, words(ctts.length, ...ctts.flat())));
  }
  // チャンク＝ trun 1本。同じコマ数のチャンクが続くところはまとめる
  const stsc = [];
  tr.chunks.forEach((c, i) => { if (!stsc.length || stsc[stsc.length - 1][1] !== c.count) stsc.push([i + 1, c.count, 1]); });
  parts.push(full('stsc', 0, 0, words(stsc.length, ...stsc.flat())));
  parts.push(full('stsz', 0, 0, words(0, tr.sizes.length, ...tr.sizes)));
  const big = tr.chunks.some((c) => c.offset >= 2 ** 32);
  if (big) {
    parts.push(full('co64', 0, 0, words(tr.chunks.length, ...tr.chunks.flatMap((c) => [Math.floor(c.offset / 2 ** 32), c.offset % 2 ** 32]))));
  } else {
    parts.push(full('stco', 0, 0, words(tr.chunks.length, ...tr.chunks.map((c) => c.offset))));
  }
  if (tr.syncs.some((s) => !s)) {
    const idx = []; tr.syncs.forEach((s, i) => { if (s) idx.push(i + 1); });
    parts.push(full('stss', 0, 0, words(idx.length, ...idx)));
  }
  return parts;
}

/** 長さの欄を書き換えた箱の写し。field＝version 0 のときの位置（version 1 は位置と幅が変わる） */
function withDuration(b, x, dur, v0, v1) {
  const out = b.slice(x.start, x.start + x.size);
  const dv = new DataView(out.buffer);
  if (out[8] === 1) { dv.setUint32(v1, Math.floor(dur / 2 ** 32)); dv.setUint32(v1 + 4, dur % 2 ** 32); }
  else dv.setUint32(v0, Math.min(dur, 0xffffffff));
  return out;
}

/** 止めたときの書き換え。戻り値 { patches: [{ position, data }], append: Uint8Array, duration（秒） }。
 *  断片に分けた MP4 でない（WebM・ふつうの MP4・途中で切れた）ときは null＝何もしない */
export function finalize(scan) {
  if (!scan || !scan.ftyp || !scan.moov || !scan.moofs.length || !scan.complete) return null;
  const b = scan.moov.bytes;
  const moov = { start: 0, head: 8, size: b.length };
  if (!child(b, moov, 'mvex')) return null; // 断片に分けていない
  const mvhd = child(b, moov, 'mvhd');
  if (!mvhd) return null;
  const movieScale = u32(b, mvhd.start + (b[mvhd.start + 8] === 1 ? 28 : 20));
  const tracks = samplesOf(scan);
  const traks = [];
  let movieDur = 0;
  for (const trak of kids(b, moov)) {
    if (trak.type !== 'trak') continue;
    const tkhd = child(b, trak, 'tkhd');
    const mdia = child(b, trak, 'mdia');
    if (!tkhd || !mdia) return null;
    const id = u32(b, tkhd.start + (b[tkhd.start + 8] === 1 ? 28 : 20));
    const tr = tracks.get(id);
    if (!tr || !tr.sizes.length) continue; // コマの無いトラックは落とす
    const mdhd = child(b, mdia, 'mdhd');
    const minf = child(b, mdia, 'minf');
    const stbl = minf && child(b, minf, 'stbl');
    const stsd = stbl && child(b, stbl, 'stsd');
    if (!mdhd || !stsd) return null;
    const mediaScale = u32(b, mdhd.start + (b[mdhd.start + 8] === 1 ? 28 : 20));
    const mediaDur = tr.durations.reduce((a, d) => a + d, 0);
    const dur = Math.round(mediaDur * movieScale / mediaScale);
    movieDur = Math.max(movieDur, dur);
    const newStbl = box('stbl', b.slice(stsd.start, stsd.start + stsd.size), ...sampleTable(tr));
    const minfKids = kids(b, minf).filter((x) => x.type !== 'stbl').map((x) => b.slice(x.start, x.start + x.size));
    const mdiaKids = kids(b, mdia).map((x) => (x.type === 'mdhd' ? withDuration(b, x, mediaDur, 24, 32)
      : x.type === 'minf' ? box('minf', ...minfKids, newStbl) : b.slice(x.start, x.start + x.size)));
    const trakKids = kids(b, trak).map((x) => (x.type === 'tkhd' ? withDuration(b, x, dur, 28, 36)
      : x.type === 'mdia' ? box('mdia', ...mdiaKids) : b.slice(x.start, x.start + x.size)));
    traks.push(box('trak', ...trakKids));
  }
  if (!traks.length) return null;
  const others = kids(b, moov).filter((x) => !['mvhd', 'trak', 'mvex'].includes(x.type)).map((x) => b.slice(x.start, x.start + x.size));
  const append = box('moov', withDuration(b, mvhd, movieDur, 24, 32), ...traks, ...others);
  const free = enc.encode('free');
  const patches = [scan.moov, ...scan.moofs].map((x) => ({ position: x.offset + 4, data: free }));
  return { patches, append, position: scan.size, duration: movieDur / movieScale };
}
