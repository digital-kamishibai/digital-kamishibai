// 作品（work.json＋素材）の読み込みと検査。定義は docs/work-format.md だけ——ここはそれに従う。
// DOM にも通信にも触らない純粋な関数だけを置く（node --test で守る）。

export const FORMAT = 'digital-kamishibai/work';
export const VERSION = 1;
export const PICTURE_EXTS = ['.jpg', '.jpeg', '.png', '.webp'];
const CUE_TYPES = new Set(['bgm', 'bgm-stop', 'sound', 'video']);
const MIME = { '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp' };

/** work.json の中身を検査する。errors が空なら work を使ってよい。 */
export function validateWork(json) {
  const errors = [];
  if (!json || typeof json !== 'object') return { work: null, errors: ['work.json is not a JSON object'] };
  if (json.format !== FORMAT) errors.push(`format must be "${FORMAT}"`);
  if (json.version !== VERSION) errors.push(`unsupported version: ${json.version} (this player reads version ${VERSION})`);
  if (typeof json.title !== 'string' || !json.title) errors.push('title is missing');
  if (typeof json.language !== 'string' || !json.language) errors.push('language is missing');
  if (!Array.isArray(json.slides) || json.slides.length === 0) {
    errors.push('slides must have at least one slide');
    return { work: null, errors };
  }
  if (json.draft !== undefined && json.draft !== true) errors.push('draft must be true when present');
  const hasLayout = json.slides.some((s) => s && s.overlay_layout !== undefined);
  if (hasLayout && !isSlideSize(json.slide_size)) errors.push('slide_size must be {width, height} in EMU when a slide has overlay_layout');
  json.slides.forEach((s, i) => {
    const where = `slide ${i + 1}`;
    if (s.number !== i + 1) errors.push(`${where}: number must be ${i + 1} (got ${s.number})`);
    if (typeof s.title !== 'string') errors.push(`${where}: title is missing`);
    if (typeof s.notes !== 'string') errors.push(`${where}: notes is missing`);
    if (s.overlays !== undefined && !isOverlays(s.overlays)) errors.push(`${where}: overlays must be boxes → paragraphs → lines of text`);
    if (s.overlay_layout !== undefined) {
      for (const e of layoutErrors(s)) errors.push(`${where}: ${e}`);
    }
    if (!Array.isArray(s.cues)) { errors.push(`${where}: cues must be a list`); return; }
    for (const c of s.cues) {
      if (!c || !CUE_TYPES.has(c.type)) errors.push(`${where}: unknown cue type ${JSON.stringify(c && c.type)}`);
      else if (c.type !== 'bgm-stop' && typeof c.file !== 'string') errors.push(`${where}: ${c.type} cue needs a file`);
      else if (c.type === 'bgm' && c.loop !== undefined && typeof c.loop !== 'boolean') errors.push(`${where}: bgm loop must be true or false`);
      else if (c.type === 'bgm' && c.start !== undefined && c.start !== 'after-video') errors.push(`${where}: bgm start must be "after-video" when present`);
      else if (c.type === 'video') for (const e of videoCueErrors(c)) errors.push(`${where}: ${e}`);
    }
    const hasVideo = s.cues.some((c) => c && c.type === 'video');
    if (!hasVideo && s.cues.some((c) => c && c.type === 'bgm' && c.start === 'after-video')) errors.push(`${where}: [BGM after video] needs a video cue on the same slide`);
    if (s.picture === null) {
      if (!hasVideo) errors.push(`${where}: picture can be null only on a slide with a video cue`);
    } else if (typeof s.picture !== 'string' || !s.picture) {
      errors.push(`${where}: picture is missing`);
    } else if (/\.heic$/i.test(s.picture)) {
      errors.push(`${where}: HEIC pictures are not accepted — export as JPEG (${s.picture})`);
    }
    if (s.picture_source !== undefined && (typeof s.picture_source !== 'string' || !s.picture_source || typeof s.picture !== 'string')) {
      errors.push(`${where}: picture_source must be the path of the picture the slide was built from`);
    }
  });
  return { work: errors.length ? null : json, errors };
}

const isTime = (v) => typeof v === 'number' && Number.isFinite(v);

/** 動画の合図が持ちうる情報（work-format §3.3）: role・seats（エンディング動画の席）・source_segments（元の動画の区間）。
 *  どれも語り手が修正票で指すためだけのもので、聞き手へは送らない */
function videoCueErrors(c) {
  const errors = [];
  if (c.role !== undefined && c.role !== 'ending') errors.push('video role must be "ending" when present');
  if (c.seats !== undefined) {
    if (c.role !== 'ending') errors.push('seats need role "ending"');
    else if (!Array.isArray(c.seats)) errors.push('seats must be a list');
    else {
      let prevTo = -Infinity;
      c.seats.forEach((t, k) => {
        const seat = `seat ${k + 1}`;
        if (!t || typeof t !== 'object') { errors.push(`${seat} must be an object`); return; }
        if (t.n !== k + 1) errors.push(`${seat}: n must be ${k + 1} (got ${t.n})`);
        if (!isTime(t.from) || !isTime(t.to) || t.from < 0 || t.from >= t.to) { errors.push(`${seat}: needs seconds from < to (from >= 0)`); return; }
        if (t.from < prevTo) errors.push(`${seat}: starts before seat ${k} ends`);
        if (t.label !== undefined && typeof t.label !== 'string') errors.push(`${seat}: label must be text`);
        if (t.pin !== undefined && (typeof t.pin !== 'string' || !t.pin)) errors.push(`${seat}: pin must be the reason, as text`);
        prevTo = t.to;
      });
    }
  }
  if (c.source_segments !== undefined) {
    if (c.role !== undefined) errors.push('source_segments are only for a video without role');
    else if (!Array.isArray(c.source_segments) || c.source_segments.length === 0) errors.push('source_segments must be a non-empty list');
    else c.source_segments.forEach((g, k) => {
      if (!g || !isTime(g.start) || !isTime(g.dur) || g.start < 0 || g.dur <= 0) errors.push(`source segment ${k + 1}: needs start >= 0 and dur > 0 (seconds)`);
    });
  }
  return errors;
}

/** overlays の形（work-format §3.2）: 枠の並び → 段落の並び → 行の並び。枠・段落は1つ以上（空の段落は [""]）。 */
function isOverlays(v) {
  const list = (x, each) => Array.isArray(x) && x.length > 0 && x.every(each);
  return Array.isArray(v) && v.every((box) => list(box, (para) => list(para, (line) => typeof line === 'string')));
}

const isLength = (v) => Number.isInteger(v);
const isColor = (v) => typeof v === 'string' && /^#[0-9A-Fa-f]{6}$/.test(v);
const ALIGNS = new Set(['left', 'center', 'right']);
const ANCHORS = new Set(['top', 'middle', 'bottom']);

function isSlideSize(v) {
  return !!v && typeof v === 'object' && isLength(v.width) && isLength(v.height) && v.width > 0 && v.height > 0;
}

/** overlay_layout の形（work-format §3.2）。overlays と同じ数・同じ段落の数で、値はすべて書き出されている。 */
function layoutErrors(s) {
  const L = s.overlay_layout;
  if (!Array.isArray(s.overlays) || !isOverlays(s.overlays)) return ['overlay_layout needs overlays'];
  if (typeof s.overlay_base !== 'string' || !s.overlay_base) return ['overlay_layout needs overlay_base'];
  if (!Array.isArray(L) || L.length !== s.overlays.length) return [`overlay_layout must have one entry per box of overlays (${s.overlays.length})`];
  const errors = [];
  L.forEach((b, k) => {
    const box = `overlay_layout box ${k + 1}`;
    const bad = (what) => errors.push(`${box}: ${what}`);
    if (!b || typeof b !== 'object') { bad('must be an object'); return; }
    if (![b.x, b.y, b.width, b.height].every(isLength) || b.width <= 0 || b.height <= 0) bad('x, y, width, height must be integers in EMU (width, height > 0)');
    if (b.rotation !== undefined && typeof b.rotation !== 'number') bad('rotation must be a number');
    if (!Array.isArray(b.inset) || b.inset.length !== 4 || !b.inset.every((v) => isLength(v) && v >= 0)) bad('inset must be [left, top, right, bottom] in EMU');
    if (!ANCHORS.has(b.anchor)) bad('anchor must be top, middle or bottom');
    if (typeof b.wrap !== 'boolean') bad('wrap must be true or false');
    if (b.shape !== undefined && b.shape !== 'rect' && b.shape !== 'roundRect') bad('shape must be rect or roundRect');
    if (b.shape === 'roundRect' && !(typeof b.corner === 'number' && b.corner >= 0 && b.corner <= 0.5)) bad('a roundRect needs corner (0 to 0.5)');
    if (b.fill !== undefined && !isColor(b.fill)) bad('fill must be #RRGGBB');
    if (b.outline !== undefined && !(b.outline && isColor(b.outline.color) && isLength(b.outline.width) && b.outline.width >= 0)) bad('outline must be {color: #RRGGBB, width: EMU}');
    if (!Array.isArray(b.paragraphs) || b.paragraphs.length !== s.overlays[k].length) { bad(`paragraphs must have one entry per paragraph of overlays (${s.overlays[k].length})`); return; }
    b.paragraphs.forEach((p, j) => {
      const ok = p && ALIGNS.has(p.align) && typeof p.space_before === 'number' && p.space_before >= 0
        && typeof p.size === 'number' && p.size > 0 && typeof p.bold === 'boolean' && isColor(p.color)
        && typeof p.font === 'string' && p.font;
      if (!ok) bad(`paragraph ${j + 1} needs align, space_before, size, bold, color (#RRGGBB) and font`);
    });
  });
  return errors;
}

/** 選ばれたファイル群から「基準フォルダからの相対パス → File」の表を作る。
 *  base: 相対パスの起点（work.json のあるフォルダ。素材フォルダだけを選んだときは選んだフォルダ）。 */
export function fileMap(entries, base) {
  const map = new Map();
  const prefix = base ? base.replace(/\/+$/, '') + '/' : '';
  for (const { path, file } of entries) {
    const p = path.replace(/\\/g, '/');
    if (prefix && !p.startsWith(prefix)) continue;
    map.set(p.slice(prefix.length), file);
  }
  return map;
}

/** 選ばれたファイル群の中の work.json の場所（そのフォルダが基準）。見つからなければ null。
 *  浅いものを優先する（見本や書き出しの中に別の work.json があっても取り違えない）。 */
export function findWorkJson(paths) {
  const hits = paths.map((p) => p.replace(/\\/g, '/')).filter((p) => p === 'work.json' || p.endsWith('/work.json'));
  if (!hits.length) return null;
  hits.sort((a, b) => a.split('/').length - b.split('/').length);
  const p = hits[0];
  return { path: p, base: p.includes('/') ? p.slice(0, p.lastIndexOf('/')) : '' };
}

function stemAndExt(path) {
  const dot = path.lastIndexOf('.');
  const slash = path.lastIndexOf('/');
  return dot > slash ? [path.slice(0, dot), path.slice(dot).toLowerCase()] : [path, ''];
}

/** work.json の絵のパスを、手元のファイルに結びつける（work-format §2.5 の拡張子の読み替えを含む）。
 *  maps は優先順（zip の中 → 素材フォルダ）。戻り値: { pictures: Map(番号 → {key, file, mime, source?}), missing: [パス] }。
 *  source＝組み立ての元の絵（picture_source）の { key, file }。絵の件の見分けに使う（_built は組み立てるたびに書き直される） */
export function resolvePictures(work, maps) {
  const pictures = new Map();
  const missing = [];
  for (const s of work.slides) {
    if (s.picture === null) continue;
    const hit = findFile(s.picture, maps);
    if (!hit) { missing.push(s.picture); continue; }
    const p = { key: hit.key, file: hit.file, mime: MIME[stemAndExt(hit.key)[1]] || 'application/octet-stream' };
    const src = s.picture_source ? findFile(s.picture_source, maps) : null;
    if (src) p.source = { key: src.key, file: src.file };
    pictures.set(s.number, p);
  }
  return { pictures, missing };
}

/** その枚の絵の候補（pictures/_candidates/NN-K.png など。gen_images.py と同じ名前・§6 picture の Use）。
 *  語り手の画面だけが使う（聞き手へ送らない）。戻り値: [{ key, file, k, mime }]（新しい K から）。同じ K は前の maps が勝つ */
export function resolveCandidates(n, maps) {
  const re = new RegExp(`^pictures/_candidates/${String(n).padStart(2, '0')}-(\\d+)(\\.(?:jpe?g|png|webp))$`, 'i');
  const byK = new Map();
  for (const map of maps) {
    for (const [key, file] of map) {
      const m = re.exec(key);
      if (!m || byK.has(Number(m[1]))) continue;
      byK.set(Number(m[1]), { key, file, k: Number(m[1]), mime: MIME[m[2].toLowerCase()] || 'application/octet-stream' });
    }
  }
  return [...byK.values()].sort((a, b) => b.k - a.k);
}

/** 文字の枠を抜いた下敷き（overlay_base）を手元のファイルに結びつける。語り手の画面だけが使う（聞き手へ送らない）。
 *  見つからない下敷きは足りない素材に数えない——絵の上で直せないだけで、上演はできる。戻り値: Map(番号 → {key, file, mime}) */
export function resolveBases(work, maps) {
  const bases = new Map();
  for (const s of work.slides) {
    if (!s.overlay_base || !s.overlay_layout) continue;
    const hit = findFile(s.overlay_base, maps);
    if (hit) bases.set(s.number, { key: hit.key, file: hit.file, mime: MIME[stemAndExt(hit.key)[1]] || 'application/octet-stream' });
  }
  return bases;
}

function findFile(path, maps) {
  const [stem] = stemAndExt(path);
  const candidates = [path, ...PICTURE_EXTS.map((e) => stem + e), ...PICTURE_EXTS.map((e) => stem + e.toUpperCase())];
  for (const map of maps) {
    for (const key of candidates) if (map.has(key)) return { key, file: map.get(key) };
  }
  return null;
}

/** work.json の動画キーを、手元のファイルに結びつける（拡張子の読み替えはしない＝§2.4 はパスそのまま）。
 *  戻り値: { videos: [{ n, k, key, file, size, mime }], missing: [パス] }。k＝その枚の何本目の動画の合図か（1から。§6 の video K）。
 *  ⚠️ 合図の中身（席・区間）は入れない——この一覧は聞き手へ配る素材の元になる。要るときは k から合図を引く */
export function resolveVideos(work, maps) {
  const videos = [];
  const missing = [];
  for (const s of work.slides) {
    let k = 0;
    for (const c of s.cues) {
      if (!c || c.type !== 'video') continue;
      k += 1;
      const hit = maps.find((m) => m.has(c.file));
      if (!hit) { if (!missing.includes(c.file)) missing.push(c.file); continue; }
      const file = hit.get(c.file);
      videos.push({ n: s.number, k, key: c.file, file, size: file.size, mime: 'video/mp4' });
    }
  }
  return { videos, missing };
}

/** 聞き手へ配る素材の一覧（同じ id は1つにまとめる。最初に出てきたものを残す）。
 *  ⚠️ 同じ動画のファイルを2つの枚で使うと、枚ごとの一覧には2回出てくる（語り手の枠には枚ごとに要る）。
 *  まとめずに配ると、同じ動画を2回送り、聞き手は保存済みの動画を上書きして開けなくなった
 *  （2026-10-24 1枚に動画が複数ある枚の確認で見つけた。1枚1本の頃からあった穴） */
export function uniqueById(items) {
  const seen = new Set();
  return items.filter((x) => (seen.has(x.id) ? false : (seen.add(x.id), true)));
}

/** 動画の見分け用の id（作品名・パス・大きさ・更新日時から。パスそのものは聞き手へ渡さない）。
 *  ハッシュは中身ではなく、この4つの文字列から取る——ブラウザは 270MB を少しずつハッシュできないため */
export async function videoId(title, key, size, lastModified) {
  const data = new TextEncoder().encode([title, key, size, lastModified].join('\n'));
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', data));
  return [...digest.slice(0, 8)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

/** BGM・効果音の素材を、手元のファイルに結びつける（同じファイルは1つにまとめる）。
 *  戻り値: { audio: [{ key, file, size, mime }], missing: [パス] } */
export function resolveAudio(work, maps) {
  const seen = new Map();
  const missing = [];
  for (const s of work.slides) {
    for (const c of s.cues) {
      if (!c || (c.type !== 'bgm' && c.type !== 'sound') || seen.has(c.file) || missing.includes(c.file)) continue;
      const hit = maps.find((m) => m.has(c.file));
      if (!hit) { missing.push(c.file); continue; }
      const file = hit.get(c.file);
      seen.set(c.file, { key: c.file, file, size: file.size, mime: /\.m4a$/i.test(c.file) ? 'audio/mp4' : 'audio/mpeg' });
    }
  }
  return { audio: [...seen.values()], missing };
}

/** 動画の中の秒 t が、エンディング動画のどの席か（work-format §3.3: from <= t < to）。どの席でもなければ null */
export function seatAt(seats, t) {
  if (!Array.isArray(seats) || !isTime(t)) return null;
  return seats.find((s) => s.from <= t && t < s.to) || null;
}

/** 切り出した動画の中の秒 t を、元の動画の秒に直す（source_segments を順につないだもの）。
 *  区間の境目ちょうどは後ろの区間の頭とみなす（最後の区間の終わりだけはその区間の終わり）。範囲の外は null。
 *  atEnd＝終わりの位置として直す（修正票の To）: 境目ちょうどは前の区間の終わりとみなす——後ろの区間の頭では、使う所が1コマも無い */
export function toSource(segments, t, atEnd = false) {
  if (!Array.isArray(segments) || !segments.length || !isTime(t) || t < 0) return null;
  let head = 0;
  for (const [k, g] of segments.entries()) {
    const last = k === segments.length - 1;
    const end = head + g.dur;
    if (atEnd && t > head && Math.abs(t - end) <= 1e-6) return { segment: k + 1, at: g.start + g.dur };
    if (t < end || (last && t <= end + 1e-6)) return { segment: k + 1, at: g.start + (t - head) };
    head += g.dur;
  }
  return null;
}
