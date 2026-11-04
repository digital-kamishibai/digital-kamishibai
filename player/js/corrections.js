// 修正票（docs/work-format.md §6）。練習しながら台本（notes）と画面の文字（overlays）を直し、
// Claude（や人）へ渡す付箋を作る。⚠️ プレイヤーは work.json を書き換えない——正本は作品の元（台本・スライド）だけ。
// DOM にも通信にも触らない純粋な関数だけを置く（node --test で守る）。
//   - 直す欄の中身 → 修正票の件（notes は変わった段落ごと・overlay は変わった枠ごと）
//   - 修正票 → いまの作品に当てた「直した後の文」（台本の欄に出す。絵は古いまま）
//   - 読み直した作品と比べた反映の判定（反映済み／手を入れて反映／未反映）
//   - 修正票の Markdown・ブラウザの中への保存の形
//   - 画面の文字の置き場所（layout。絵の上で動かした枠の位置・大きさ・文字の大きさ・文字色・下地の色。計算は layout.js）
//   - エンディング動画のコマ（seat。止めた位置のコマを「差し替えたい」と指す。§6 ending seat N）——
//     文ではないので Before/After で判定せず、指したときの写真の名前・動画のファイルが変わったら「変わった（見て消す）」。自分では消さない
//   - 上演中の動画の区間（video。止めた位置を「開始に／終わりに」。§6 video K）——コマと同じく判定せず、動画のファイルか元の区間が変わったら「変わった」
//   - 絵の作り直し（picture。何をどう直したいかの文が必須。§6 picture）——1枚に1件。絵のパスかファイルが変わったら「変わった」。
//     候補（pictures/_candidates）から選んだときは Use（文は任意）。絵が変わって候補が無くなったら反映済み
// ⚠️ 修正票は聞き手へ送らない（R1。notes・overlays と同じ）。語り手の端末の外へ出るのは、コピーとファイルへの保存だけ

import { diffLayout, layoutLines, judgeLayout, applyLayoutItem, isLayoutValues } from './layout.js';
import { toSource } from './work.js';

export const SHEET_VERSION = 1;
export const storageKey = (title) => `dk-corrections:${title}`;

/** 直す欄を出してよいか。練習用の版（draft）で、受付を開いていないときだけ（E1・決定5） */
export const editable = (ctx) => !!(ctx && ctx.draft && !ctx.roomOpen);
/** 修正票を読み書きしてよいか（E5）。練習用の版のときだけ——家族が同じブラウザで配った版を開いても、練習した人の未反映の文を出さない */
export const sheetEnabled = (work) => !!(work && work.draft === true);
/** 作品を読み直してよいか（E10）。受付中は不可（聞き手へ配った絵・動画の一覧と食い違う） */
export const mayReload = (ctx) => !!(ctx && ctx.hasWork && !ctx.roomOpen);
/** 直す欄の開け閉め（E1）。open＝開いている枚（閉じていれば null）。
 *  ev: { type: 'open', slide } | 'close'（閉じて修正票に入れる）| 'cancel'（入れずに閉じる）| 'move'（枚を動かした）| 'room'（受付を開いた）。
 *  戻り値 { open, commit }。commit＝書いたものを修正票に入れる（受付を開いたときも、書きかけは修正票の下書きとして残す） */
export function editorStep(open, ev, ctx) {
  const type = ev && ev.type;
  if (type === 'open') return editable(ctx) ? { open: ev.slide, commit: open != null && open !== ev.slide } : { open: null, commit: open != null };
  if (type === 'cancel') return { open: null, commit: false };
  if (['close', 'move', 'room'].includes(type)) return { open: null, commit: open != null };
  return { open, commit: false };
}

/** 読み直したあとの枚。今の枚を保ち、枚数が減っていたら最後の枚へ */
export const keepSlide = (cur, count) => Math.max(1, Math.min(Number(cur) || 1, count));

const trimEnds = (text) => String(text).split('\n').map((l) => l.replace(/[ \t　]+$/, '')).join('\n');
const isBlank = (line) => /^[ \t　]*$/.test(line);

/** notes → 段落の並び（1行以上の空行で区切る。各行の行末の空白はそろえる） */
export function paragraphs(notes) {
  const out = [];
  let cur = [];
  for (const line of String(notes || '').split('\n')) {
    if (isBlank(line)) { if (cur.length) { out.push(cur.join('\n')); cur = []; } }
    else cur.push(line.replace(/[ \t　]+$/, ''));
  }
  if (cur.length) out.push(cur.join('\n'));
  return out;
}

export const joinParagraphs = (paras) => paras.join('\n\n');

/** 枠（段落の並び → 行の並び）を比べられる形に（行末の空白をそろえる） */
export const normBox = (box) => (box || []).map((para) => para.map((l) => l.replace(/[ \t　]+$/, '')));
const sameBox = (a, b) => JSON.stringify(normBox(a)) === JSON.stringify(normBox(b));
/** 枠 → 文字（行は改行・段落は空行1つ） */
export const boxText = (box) => (box || []).map((para) => para.join('\n')).join('\n\n');

/** 枠の直す欄（段落ごとの欄。決定4）→ 枠。欄の中の改行＝段落内改行。
 *  fields: [{ text, orig }]（orig＝元の段落の文。足した欄は null）。
 *  空にした欄は消す——ただし、もともと空の段落（行間）はそのまま残す。全部消したら [] ＝枠を消す */
export function boxFromFields(fields) {
  const out = [];
  for (const f of fields || []) {
    const text = String(f.text == null ? '' : f.text);
    if (!text.trim() && f.orig !== '') continue;
    out.push(text.split('\n'));
  }
  return out;
}

/** 枠 → 直す欄の初期値 */
export const fieldsFromBox = (box) => (box || []).map((para) => ({ text: para.join('\n'), orig: para.join('\n') }));

// ---------- 差分 → 修正票の件 ----------

/** 段落の並びの最長共通部分で、変わったところの塊を出す → [{ i0, i1, j0, j1 }]（before[i0..i1) → after[j0..j1)） */
function hunks(a, b) {
  const n = a.length, m = b.length;
  const L = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = a[i] === b[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const out = [];
  let i = 0, j = 0, open = null;
  const close = () => { if (open) { out.push({ ...open, i1: i, j1: j }); open = null; } };
  while (i < n || j < m) {
    if (i < n && j < m && a[i] === b[j]) { close(); i++; j++; continue; }
    if (!open) open = { i0: i, j0: j };
    if (j < m && (i >= n || L[i][j + 1] >= L[i + 1][j])) j++; else i++;
  }
  close();
  return out;
}

/** notes の直す前 → 直した後 → 件の並び（変わった段落ごと。足した・消したときは、変わっていない段落を頼りに並べる） */
export function diffNotes(slide, before, after) {
  const a = paragraphs(before), b = paragraphs(after);
  const items = [];
  for (const h of hunks(a, b)) {
    const k = h.i1 - h.i0, m = h.j1 - h.j0;
    if (k === m) {
      for (let x = 0; x < k; x++) {
        if (a[h.i0 + x] !== b[h.j0 + x]) items.push({ slide, kind: 'notes', at: [h.i0 + x + 1, h.i0 + x + 1], before: [a[h.i0 + x]], after: [b[h.j0 + x]] });
      }
      continue;
    }
    let bef = a.slice(h.i0, h.i1), aft = b.slice(h.j0, h.j1), from = h.i0;
    if (!k && a.length) {
      // 足しただけ: 直前（先頭なら直後）の変わっていない段落を一緒に運ぶ（元の文を空にしない）
      if (h.i0 > 0) { bef = [a[h.i0 - 1]]; aft = [a[h.i0 - 1], ...aft]; from = h.i0 - 1; }
      else { bef = [a[0]]; aft = [...aft, a[0]]; }
    }
    items.push({ slide, kind: 'notes', at: [from + 1, from + Math.max(bef.length, 1)], before: bef, after: aft });
  }
  return items;
}

/** 画面の文字の直す前（枠の並び）→ 直した後（同じ数の枠。[] ＝消した）→ 件の並び（変わった枠ごと） */
export function diffOverlays(slide, before, after) {
  const items = [];
  (before || []).forEach((box, i) => {
    const next = after && after[i] !== undefined ? after[i] : box;
    if (!sameBox(box, next)) items.push({ slide, kind: 'overlay', at: i + 1, before: normBox(box), after: normBox(next) });
  });
  return items;
}

// ---------- 修正票 ----------

export const emptySheet = (title) => ({ v: SHEET_VERSION, title: String(title), items: [], comments: {}, commentAt: {} });

/** 作品の中身のしるし（ひとことを書いたときの作品と、読み直した作品が同じか。FNV-1a 32bit。2026-10-26）。
 *  ひとことはプレイヤーが判定できないので、作品が変わったら「見て消す」、変わっていなければ「未反映」と数える */
export function workSig(work) {
  const s = JSON.stringify(work);
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
  return h.toString(16).padStart(8, '0');
}

/** ひとことを消す（しるしも一緒に） */
function dropComment(comments, commentAt, n) {
  delete comments[n];
  delete commentAt[n];
}

const itemsOf = (sheet, slide) => sheet.items.filter((x) => x.slide === slide);

/** その枚の直す欄を閉じた: いまの作品の文と比べて件を作り直す。
 *  元の文がもう見つからない件（手を入れて反映＝練習した人が見て消すもの）は、そのまま残す */
export function setSlideEdits(sheet, slideData, edits, sig) {
  const n = slideData.number;
  // 指したコマ・動画の区間は直す欄の外で足したもの。欄を閉じても残す
  const keep = itemsOf(sheet, n).filter((x) => isMedia(x) || judge(x, slideData) === 'reworded');
  const fresh = [];
  if (edits.notes !== undefined) fresh.push(...diffNotes(n, slideData.notes, edits.notes));
  if (edits.overlays !== undefined) fresh.push(...diffOverlays(n, slideData.overlays, edits.overlays));
  if (edits.layout !== undefined) {
    (slideData.overlay_layout || []).forEach((box, i) => {
      const item = edits.layout[i] ? diffLayout(n, i + 1, box, edits.layout[i], (slideData.overlays || [])[i]) : null;
      if (item) fresh.push(item);
    });
  }
  const items = [...sheet.items.filter((x) => x.slide !== n), ...keep, ...fresh].sort(order);
  const comments = { ...sheet.comments };
  const commentAt = { ...(sheet.commentAt || {}) };
  // comment が undefined＝ひとことの欄に触れていない（前回のひとことを欄に入れずに開いた）。そのまま残す
  const c = edits.comment === undefined ? null : String(edits.comment || '').replace(/\s+/g, ' ').trim();
  if (c === null) { /* そのまま */ } else if (!c) dropComment(comments, commentAt, n);
  else if (comments[n] !== c || !commentAt[n]) {  // 書いた・書き替えたときだけ、いまの作品のしるしを付け直す
    comments[n] = c;
    if (sig) commentAt[n] = sig; else delete commentAt[n];
  }
  return { ...sheet, items, comments, commentAt };
}

const KIND_ORDER = { notes: 0, overlay: 1, layout: 2, picture: 3, video: 4, seat: 5 };
/** 絵・動画の件（文ではない。Before/After を持たず、判定は「変わった」かどうかだけ） */
export const isMedia = (x) => x.kind === 'seat' || x.kind === 'video' || x.kind === 'picture';
/** その件が指す動画は、枚の何本目か（コマは video・区間は at。絵の件は動画を指さない＝null） */
export const videoOf = (x) => (x.kind === 'seat' ? x.video : x.kind === 'video' ? x.at : null);
function order(a, b) {
  if (a.slide !== b.slide) return a.slide - b.slide;
  if (a.kind !== b.kind) return KIND_ORDER[a.kind] - KIND_ORDER[b.kind];
  const pos = (x) => (x.kind === 'notes' ? x.at[0] : x.kind === 'picture' ? 0 : x.at);
  return pos(a) - pos(b);
}

// ---------- 絵の作り直し（picture） ----------

/** 絵の件で見る絵のパス: 組み立ての元の絵（picture_source）があればそれ。文字を載せた絵（_built）は組み立てるたびに
 *  書き直されるので、それで見分けると、絵が同じでも「変わった」になる（2026-11-01 Issue #5） */
export const picturePath = (slideData) => slideData.picture_source || slideData.picture;

/** その枚の絵を作り直したい: 何をどう直したいかの文（必須。空なら sheet をそのまま返す）を修正票に入れる。1枚に1件（書き直せば置き換える）。
 *  指したときの絵のパス（picturePath: 組み立ての元の絵があればそれ）と file＝その絵のファイルの見分け（{ size, modified }）を持つ（M6。Markdown には書かない）。
 *  絵の無い枚（picture: null）でも sheet をそのまま返す */
export function askPicture(sheet, slideData, file, comment) {
  const c = String(comment || '').replace(/\s+/g, ' ').trim();
  if (!c || typeof slideData.picture !== 'string' || !slideData.picture) return sheet;
  const item = { slide: slideData.number, kind: 'picture', path: picturePath(slideData), comment: c };
  if (file) item.file = { size: file.size, modified: file.modified };
  const same = (x) => x.kind === 'picture' && x.slide === item.slide;
  return { ...sheet, items: [...sheet.items.filter((x) => !same(x)), item].sort(order) };
}

/** 候補から選ぶ: use＝選んだ候補のパス（pictures/_candidates/NN-K.png）。その枚の絵の件を置き換える（作り直しの頼みも）。
 *  comment は任意。file＝いまの絵のファイルの見分け（askPicture と同じ）。絵の無い枚・use が空なら sheet をそのまま返す */
export function choosePicture(sheet, slideData, file, use, comment = '') {
  const u = String(use || '').trim();
  if (!u || typeof slideData.picture !== 'string' || !slideData.picture) return sheet;
  const item = { slide: slideData.number, kind: 'picture', path: picturePath(slideData), use: u };
  const c = String(comment || '').replace(/\s+/g, ' ').trim();
  if (c) item.comment = c;
  if (file) item.file = { size: file.size, modified: file.modified };
  const same = (x) => x.kind === 'picture' && x.slide === item.slide;
  return { ...sheet, items: [...sheet.items.filter((x) => !same(x)), item].sort(order) };
}

/** 絵の件が、いまの作品でどうなったか → 'changed'（絵のパスかファイルが変わった）| 'pending' |
 *  'done'（候補から選んだ件で、絵が変わり、選んだ候補がもう無い＝--use で差し替えた）。
 *  file＝いまの絵のファイルの見分け（分からなければ null＝パスだけで見る）。Use の件は file.useLeft＝選んだ候補がまだあるか。
 *  ⚠️ 候補を作っただけ（pictures/_candidates に増えただけ）では絵は変わらないので 'pending' のまま */
function judgePicture(item, slideData, file) {
  // 元の絵を持つ前に、組み立てた絵（_built）で見分けを取った件: その見分けはもう比べられないので、パスだけで見る
  if (slideData.picture_source && item.path !== slideData.picture_source && item.path === slideData.picture) {
    return item.use && file && file.useLeft === false ? 'done' : 'pending';
  }
  const changed = picturePath(slideData) !== item.path
    || !!(file && item.file && (file.size !== item.file.size || file.modified !== item.file.modified));
  if (!changed) return 'pending';
  return item.use && file && file.useLeft === false ? 'done' : 'changed';
}

/** 絵の件の行（§6: Use＝選んだ候補・Comment。Use が無ければ Comment は必須） */
export const pictureLines = (x) => [...(x.use ? [`Use ${x.use}`] : []), ...(x.comment ? [`Comment: ${x.comment}`] : [])];

// ---------- エンディング動画のコマ（seat） ----------

/** その枚の k 本目の動画の合図（cues の動画だけを数える。1から） */
export const videoCueOf = (slideData, k) => (slideData.cues || []).filter((c) => c && c.type === 'video')[k - 1] || null;

/** コマを指す: 止めた位置 time（動画の中の秒）のコマを、修正票に入れる。同じ動画の同じコマは1件にまとめる（ひとことを書き替える）。
 *  file＝指したときの動画のファイルの見分け（{ size, modified }）。コマが無い位置なら sheet をそのまま返す */
export function pointSeat(sheet, slideData, k, seats, time, file, comment = '') {
  const seat = (seats || []).find((t) => t.from <= time && time < t.to);
  if (!seat) return sheet;
  const item = { slide: slideData.number, kind: 'seat', at: seat.n, video: k, time: Math.round(time * 10) / 10 };
  if (seat.label !== undefined) item.label = seat.label;
  if (seat.pin) item.pin = seat.pin;
  if (file) item.file = { size: file.size, modified: file.modified };
  const c = String(comment || '').replace(/\s+/g, ' ').trim();
  if (c) item.comment = c;
  const same = (x) => x.kind === 'seat' && x.slide === item.slide && x.video === k && x.at === seat.n;
  return { ...sheet, items: [...sheet.items.filter((x) => !same(x)), item].sort(order) };
}

// ---------- 上演中の動画の区間（video K） ----------

const tenth = (t) => Math.round(t * 10) / 10;

/** 区間の端を入れる: side＝'from'（いまの位置を開始に）| 'to'（終わりに）、time＝動画の中の秒。同じ動画は1件にまとめる。
 *  元の動画の区間（source_segments）があれば、元の動画での秒も持つ（Markdown の (source m:ss.s)。M3）。
 *  反対の端と食い違う（開始が終わり以降になる）ときは、反対の端を外す——語り手の画面のいまの区間に出るので、食い違いを黙って残さない。
 *  comment: 文字なら書き替える（空なら消す）・undefined なら前のひとことを保つ。
 *  file＝指したときの動画のファイルの見分け。エンディング動画（role あり）・動画の無い番号なら sheet をそのまま返す */
export function markCut(sheet, slideData, k, side, time, file, comment) {
  const cue = videoCueOf(slideData, k);
  if (!cue || cue.role !== undefined || !['from', 'to'].includes(side) || !(time >= 0)) return sheet;
  const same = (x) => x.kind === 'video' && x.slide === slideData.number && x.at === k;
  const old = sheet.items.find(same);
  const segs = Array.isArray(cue.source_segments) && cue.source_segments.length ? cue.source_segments : null;
  const item = { slide: slideData.number, kind: 'video', at: k };
  const put = (end, t) => {
    item[end] = t;
    const src = segs ? toSource(segs, t, end === 'to') : null;
    if (src) item[`${end}Source`] = tenth(src.at);
  };
  const t = tenth(time);
  const other = side === 'from' ? 'to' : 'from';
  const keep = old && old[other] !== undefined && (side === 'from' ? t < old.to : old.from < t);
  // 書く順を From → To にそろえる（保存の形を比べやすく）
  if (side === 'to' && keep) put('from', old.from);
  put(side, t);
  if (side === 'from' && keep) put('to', old.to);
  if (segs) item.segments = segs.map((g) => ({ start: g.start, dur: g.dur }));
  if (file) item.file = { size: file.size, modified: file.modified };
  const c = comment === undefined ? (old && old.comment) || '' : String(comment).replace(/\s+/g, ' ').trim();
  if (c) item.comment = c;
  return { ...sheet, items: [...sheet.items.filter((x) => !same(x)), item].sort(order) };
}

/** 区間の件が、いまの作品でどうなったか → 'changed'（動画のファイルか元の区間が変わった・その動画が無い）| 'pending' */
function judgeCut(item, slideData, file) {
  const cue = videoCueOf(slideData, item.at);
  if (!cue || cue.role !== undefined) return 'changed';
  const now = Array.isArray(cue.source_segments) ? cue.source_segments.map((g) => ({ start: g.start, dur: g.dur })) : undefined;
  if (JSON.stringify(now) !== JSON.stringify(item.segments)) return 'changed';
  if (file && item.file && (file.size !== item.file.size || file.modified !== item.file.modified)) return 'changed';
  return 'pending';
}

/** 区間の件の行（§6: From・To・Comment。元の動画の秒があれば (source m:ss.s)） */
export function cutLines(x) {
  const out = [];
  const line = (word, t, src) => out.push(`${word} ${clock(t)}${src !== undefined ? ` (source ${clock(src)})` : ''}`);
  if (x.from !== undefined) line('From', x.from, x.fromSource);
  if (x.to !== undefined) line('To', x.to, x.toSource);
  if (x.comment) out.push(`Comment: ${x.comment}`);
  return out;
}

/** 指したコマが、いまの作品でどうなったか → 'changed'（写真の名前か動画のファイルが変わった）| 'pending'。
 *  file＝いまの動画のファイルの見分け（分からなければ null＝写真の名前だけで見る） */
function judgeSeat(item, slideData, file) {
  const cue = videoCueOf(slideData, item.video);
  const seat = cue && Array.isArray(cue.seats) ? cue.seats.find((t) => t.n === item.at) : null;
  if (!seat || seat.label !== item.label) return 'changed';
  if (file && item.file && (file.size !== item.file.size || file.modified !== item.file.modified)) return 'changed';
  return 'pending';
}

/** 1件を消す（手を入れて反映した件を、練習した人が見て消す） */
export function removeItem(sheet, index) {
  const items = sheet.items.filter((_, i) => i !== index);
  const comments = { ...sheet.comments };
  const commentAt = { ...(sheet.commentAt || {}) };
  const n = sheet.items[index] && sheet.items[index].slide;
  if (n && !items.some((x) => x.slide === n)) dropComment(comments, commentAt, n);
  return { ...sheet, items, comments, commentAt };
}

export function removeComment(sheet, slide) {
  const comments = { ...sheet.comments };
  const commentAt = { ...(sheet.commentAt || {}) };
  dropComment(comments, commentAt, slide);
  return { ...sheet, comments, commentAt };
}

// ---------- 当てる・判定する（E6・E10） ----------

/** 段落の並びの中で、seq が続けて現れる位置（無ければ -1。空の seq は 0） */
function findRun(paras, seq) {
  if (!seq.length) return 0;
  for (let i = 0; i + seq.length <= paras.length; i++) if (seq.every((p, k) => paras[i + k] === p)) return i;
  return -1;
}

/** 修正票の1件を、読み直した作品の同じ枚と比べる → 'done'（反映済み）| 'reworded'（手を入れて反映）| 'pending'（未反映）。
 *  絵（picture）・コマ（seat）・動画の区間（video）は 'changed'（変わった・見て消す）| 'pending'。fileOf(item)＝その件の動画のいまのファイルの見分け（任意） */
export function judge(item, slideData, fileOf) {
  if (item.kind === 'picture') return judgePicture(item, slideData, fileOf ? fileOf(item) : null);
  if (item.kind === 'seat') return judgeSeat(item, slideData, fileOf ? fileOf(item) : null);
  if (item.kind === 'video') return judgeCut(item, slideData, fileOf ? fileOf(item) : null);
  if (item.kind === 'layout') return judgeLayout(item, slideData);
  const found = (x) => (item.kind === 'notes'
    ? findRun(paragraphs(slideData.notes).map(trimEnds), x.map(trimEnds)) >= 0
    : (slideData.overlays || []).some((b) => sameBox(b, x)));
  // 消した件は「元の文が残っているか」だけで決める（空の新しい文で探すと、どこにでも見つかって必ず反映済みになる）
  if (!item.after.length) return item.before.length && found(item.before) ? 'pending' : 'done';
  if (found(item.after)) return 'done';
  return found(item.before) ? 'pending' : 'reworded';
}

/** 作品を読み直した（E10）。反映済みの件は自動で消し、ほかは判定を付けて返す。
 *  直した件が全部消えた枚の「ひとこと」も消す（文を直さないひとことは、練習した人が消すまで残す）。
 *  まだ件の残る枚のひとことは、いまの作品のしるしに付け直す（その件の理由として生きている）。
 *  ひとことだけが残った枚は、書いたときのしるしのまま＝前回のひとこと（isOldComment）。
 *  2026-10-29: 前回のひとことが、次の練習でその枚に足した直しの Comment: として修正票に出た（実際の作品で） */
export function reconcile(sheet, work, fileOf) {
  const slide = (n) => work.slides[n - 1];
  const gone = (x) => (isMedia(x) ? 'changed' : 'reworded');
  const judged = sheet.items.map((x) => ({ x, st: slide(x.slide) ? judge(x, slide(x.slide), fileOf) : gone(x) }));
  const items = judged.filter((j) => j.st !== 'done').map((j) => j.x);
  const comments = { ...sheet.comments };
  const commentAt = { ...(sheet.commentAt || {}) };
  for (const n of Object.keys(comments)) {
    const had = sheet.items.some((x) => x.slide === Number(n));
    if (had && !items.some((x) => x.slide === Number(n))) dropComment(comments, commentAt, n);
  }
  const sig = workSig(work);
  let resigned = 0;
  for (const n of Object.keys(comments)) {
    if (items.some((x) => x.slide === Number(n)) && commentAt[n] !== sig) { commentAt[n] = sig; resigned++; }
  }
  return {
    sheet: { ...sheet, items, comments, commentAt },
    resigned,
    done: judged.filter((j) => j.st === 'done').length,
    status: judged.filter((j) => j.st !== 'done').map((j) => j.st),
  };
}

/** 修正票を、いまの作品の1枚に当てる（E6）→ { notes, overlays, layout, edited: { notes, boxes: Set(番号), layout: Set(番号) } }。
 *  当てられるのは元の文・元の値が見つかる件だけ（手を入れて反映した件は当てない）。overlays の消した枠は null。
 *  layout は枠ごとに直した値（EMU・pt・色。直していなければ null） */
export function applySheet(sheet, slideData) {
  let paras = paragraphs(slideData.notes);
  const boxes = (slideData.overlays || []).map((b) => normBox(b));
  const layout = (slideData.overlay_layout || []).map(() => null);
  const edited = { notes: false, boxes: new Set(), layout: new Set() };
  for (const x of itemsOf(sheet, slideData.number)) {
    if (isMedia(x)) continue; // 文ではない（台本の欄にも画面の文字にも当てない）
    if (x.kind === 'layout') {
      const box = (slideData.overlay_layout || [])[x.at - 1];
      const e = box ? applyLayoutItem(x, box, (slideData.overlays || [])[x.at - 1]) : null;
      if (e) { layout[x.at - 1] = e; edited.layout.add(x.at); }
    } else if (x.kind === 'notes') {
      if (!x.before.length && paras.length) continue; // 空の台本に書き足した件。台本がもう空でなければ当てない
      const at = findRun(paras, x.before);
      if (at < 0) continue;
      paras = [...paras.slice(0, at), ...x.after, ...paras.slice(at + x.before.length)];
      edited.notes = true;
    } else {
      const at = boxes.findIndex((b, i) => b && !edited.boxes.has(i + 1) && sameBox(b, x.before));
      if (at < 0) continue;
      boxes[at] = x.after.length ? x.after : null;
      edited.boxes.add(at + 1);
    }
  }
  return { notes: edited.notes ? joinParagraphs(paras) : slideData.notes, overlays: boxes, layout, edited };
}

// ---------- Markdown（§6）と保存の形 ----------

/** 囲み（` の数は、本文中にある最も長い ` の並びより1つ多く。3つ以上） */
export function fence(text) {
  const longest = Math.max(0, ...(String(text).match(/`+/g) || []).map((s) => s.length));
  const f = '`'.repeat(Math.max(3, longest + 1));
  return `${f}\n${text}\n${f}`;
}

const pad = (n) => String(n).padStart(2, '0');
const stamp = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;

export const place = (x) => (x.kind === 'notes' ? `notes ${x.at[0] === x.at[1] ? x.at[0] : `${x.at[0]}-${x.at[1]}`}`
  : x.kind === 'seat' ? `ending seat ${x.at}` : x.kind === 'picture' ? 'picture' : `${x.kind} ${x.at}`);
/** 動画の中の秒 → m:ss.s（§6） */
export function clock(sec) {
  const tenths = Math.round(Math.max(0, Number(sec) || 0) * 10);
  const m = Math.floor(tenths / 600);
  const rest = (tenths - m * 600) / 10;
  return `${m}:${rest.toFixed(1).padStart(4, '0')}`;
}
/** コマの件の行（§6: At・Label・Pin・Comment） */
export function seatLines(x) {
  const out = [`At ${clock(x.time)}`];
  if (x.label) out.push(`Label ${x.label}`);
  if (x.pin) out.push(`Pin ${x.pin}`);
  if (x.comment) out.push(`Comment: ${x.comment}`);
  return out;
}
export const textOf = (x, side) => (x.kind === 'notes' ? joinParagraphs(x[side]) : x.kind === 'layout' ? layoutLines(x[side]) : boxText(x[side]));

/** 絵・動画の件の行（見出しの下） */
export const mediaLines = (x) => (x.kind === 'seat' ? seatLines(x) : x.kind === 'picture' ? pictureLines(x) : cutLines(x));

/** 修正票 → Markdown。skip＝書かない件の番号（手を入れて反映した件。Claude にもう一度当てさせない）。
 *  sig＝いまの作品のしるし。渡したら、前回のひとこと（isOldComment＝見て消す）は書かない——
 *  書くと、その枚に今回足した直しの Comment: に見える（2026-10-29 実際の作品で） */
export function sheetMarkdown(sheet, date, skip = new Set(), sig) {
  const out = [`# Correction sheet: ${sheet.title} (${stamp(date)})`];
  const slides = new Set([...sheet.items.map((x) => x.slide), ...Object.keys(sheet.comments).map(Number)]);
  for (const n of [...slides].sort((a, b) => a - b)) {
    const mine = sheet.items.map((x, i) => ({ x, i })).filter((e) => e.x.slide === n);
    const list = mine.filter((e) => !skip.has(e.i) && !isMedia(e.x));
    const media = mine.filter((e) => !skip.has(e.i) && isMedia(e.x));
    const comment = sig !== undefined && isOldComment(sheet, n, sig) ? undefined : sheet.comments[n];
    // その枚のひとことは、文の件の最後に付ける。文の件が無ければ comment の見出しで（絵・動画の件は自分のひとことを持つ）
    if (!list.length) {
      if (comment && !mine.some((e) => !isMedia(e.x))) out.push('', `## [Slide ${n}] comment`, `Comment: ${comment}`);
    }
    list.forEach(({ x }, k) => {
      out.push('', `## [Slide ${n}] ${place(x)}`, '### Before', fence(textOf(x, 'before')), '### After', fence(textOf(x, 'after')));
      if (comment && k === list.length - 1) out.push(`Comment: ${comment}`);
    });
    for (const { x } of media) out.push('', `## [Slide ${n}] ${place(x)}`, ...mediaLines(x));
  }
  return out.join('\n') + '\n';
}

/** 保存するファイルの名前の案（作品名＋日時） */
export function sheetName(title, date) {
  const safe = String(title || 'kamishibai').replace(/[\\/:*?"<>|\u0000-\u001f]/g, '').replace(/\s+/g, ' ').trim().slice(0, 60) || 'kamishibai';
  return `${safe}-corrections-${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}-${pad(date.getHours())}${pad(date.getMinutes())}.md`;
}

const isStrList = (v) => Array.isArray(v) && v.every((s) => typeof s === 'string');
const isBoxShape = (v) => Array.isArray(v) && v.every(isStrList);
const isFile = (f) => f === undefined || (!!f && typeof f.size === 'number' && typeof f.modified === 'number');

/** ブラウザの中に保存した修正票を読む（形が違えば空の票。別の作品の票は使わない） */
export function readSheet(raw, title) {
  let j;
  try { j = JSON.parse(raw); } catch { return emptySheet(title); }
  if (!j || j.v !== SHEET_VERSION || j.title !== title || !Array.isArray(j.items)) return emptySheet(title);
  const items = j.items.filter((x) => x && Number.isInteger(x.slide) && (
    (x.kind === 'notes' && isStrList(x.before) && isStrList(x.after) && Array.isArray(x.at))
    || (x.kind === 'overlay' && isBoxShape(x.before) && isBoxShape(x.after) && Number.isInteger(x.at))
    || (x.kind === 'layout' && isLayoutValues(x.before) && isLayoutValues(x.after) && Number.isInteger(x.at))
    || (x.kind === 'seat' && Number.isInteger(x.at) && Number.isInteger(x.video) && typeof x.time === 'number'
      && (x.label === undefined || typeof x.label === 'string') && (x.pin === undefined || typeof x.pin === 'string')
      && (x.comment === undefined || typeof x.comment === 'string')
      && isFile(x.file))
    || (x.kind === 'picture' && typeof x.path === 'string' && !!x.path && isFile(x.file)
      && (x.use === undefined || (typeof x.use === 'string' && !!x.use))
      && (x.comment === undefined ? x.use !== undefined : typeof x.comment === 'string' && !!x.comment))
    || (x.kind === 'video' && Number.isInteger(x.at) && (x.from !== undefined || x.to !== undefined)
      && ['from', 'to', 'fromSource', 'toSource'].every((k) => x[k] === undefined || typeof x[k] === 'number')
      && (x.comment === undefined || typeof x.comment === 'string') && isFile(x.file)
      && (x.segments === undefined || (Array.isArray(x.segments) && x.segments.every((g) => g && typeof g.start === 'number' && typeof g.dur === 'number'))))));
  const comments = {};
  for (const [k, v] of Object.entries(j.comments || {})) if (typeof v === 'string' && v) comments[k] = v;
  const commentAt = {};
  for (const [k, v] of Object.entries(j.commentAt || {})) if (comments[k] && typeof v === 'string' && /^[0-9a-f]{8}$/.test(v)) commentAt[k] = v;
  return { v: SHEET_VERSION, title, items, comments, commentAt };
}

export const isEmpty = (sheet) => !sheet.items.length && !Object.keys(sheet.comments).length;

/** 文の件の無い枚のひとことが、いまの作品でどうなったか → 'pending'（書いたときの作品のまま）| 'changed'（作品が変わった・しるしが無い＝見て消す）。
 *  ⚠️ 作品が変わっても、そのひとことが済んだとは限らない（自分では消さない）。作品を変えずに直した（プレイヤーを直した等）ひとことは未反映のまま */
export const commentStatus = (sheet, n, sig) => ((sheet.commentAt || {})[n] && (sheet.commentAt || {})[n] === sig ? 'pending' : 'changed');

/** 文の件の無い枚のひとこと（枚の番号） */
export const loneComments = (sheet) => Object.keys(sheet.comments).filter((k) => !sheet.items.some((x) => x.slide === Number(k)));

/** 前回のひとこと: 書いたあと作品が変わり、件の理由としても付け直されていない（reconcile）。
 *  その枚にあとから直しを足しても、その直しの理由ではない——一覧では「見て消す」に、修正票には書かない */
export const isOldComment = (sheet, n, sig) => !!sheet.comments[n] && (sheet.commentAt || {})[n] !== sig;

/** 一覧に「ひとこと」の行として出す枚: 文の件の無い枚と、前回のひとことの枚 */
const commentRows = (sheet, sig) => Object.keys(sheet.comments)
  .filter((k) => !sheet.items.some((x) => x.slide === Number(k)) || isOldComment(sheet, k, sig));

/** 修正票の件を、ボタンと一覧で同じ見出しに分ける（2026-10-27 練習した人「ボタンの数と詳細の関係が分からない」）。
 *  stOf(x)＝その件の判定・sig＝いまの作品のしるし。→ { pending, look, done }。各行は { kind: 'item', i, slide, st } か { kind: 'comment', slide, st }。
 *  pending＝未反映（まだ作品に入っていない）・look＝見て消す（手を入れて反映・変わった）・done＝反映済み（開き直すと消える）。枚の順 */
export function sheetGroups(sheet, stOf, sig) {
  const rows = [
    ...sheet.items.map((x, i) => ({ kind: 'item', i, slide: x.slide, st: stOf(x) })),
    ...commentRows(sheet, sig).map((n) => ({ kind: 'comment', slide: Number(n), st: commentStatus(sheet, n, sig) })),
  ].sort((a, b) => a.slide - b.slide);
  return {
    pending: rows.filter((r) => r.st === 'pending'),
    look: rows.filter((r) => r.st === 'reworded' || r.st === 'changed'),
    done: rows.filter((r) => r.st === 'done'),
  };
}

/** 修正票のボタンに出す数（2026-10-26: 直った後も数が残って「まだ直っていない」と読まれた）。一覧の見出しと同じ数（sheetGroups） */
export function sheetCounts(sheet, stOf, sig) {
  const g = sheetGroups(sheet, stOf, sig);
  return { pending: g.pending.length, look: g.look.length, done: g.done.length };
}
