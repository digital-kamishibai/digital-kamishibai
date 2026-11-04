// 画面の文字の置き場所（docs/work-format.md §3.2 の overlay_layout・§6 の layout）。絵の上で枠を動かす・大きさを変える。
// DOM にも通信にも触らない純粋な関数だけを置く（node --test で守る）。
//   - 枠の位置・大きさ（EMU）と文字の大きさ（pt）の直し: 0.01インチ・1pt 刻み、中央への吸い付き
//   - 文字色（color）と下地の色（fill。null＝下地なし＝修正票の fill none）の直し・明暗差の目安（§3.2）
//   - 直し → 修正票の件（変わった値だけ。インチ小数2桁・整数 pt）・読み直した作品と比べた反映の判定
//   - 描き方: スライドの寸法 → 画面の px（1行＝1.2×大きさ・空の段落も1行。段階0で PowerPoint と ±2〜3px）
// ⚠️ ここで描くのは「動かすための下書き」。聞き手に見せるのは、いつも PowerPoint が描いた絵（L8）

export const EMU_PER_IN = 914400;
export const EMU_PER_PT = 12700;
export const STEP = EMU_PER_IN / 100;            // 矢印キーの1刻み＝0.01インチ（修正票と同じ刻み）
export const BIG_STEP = EMU_PER_IN / 10;         // Shift＋矢印＝0.1インチ
export const KEYS = ['left', 'top', 'width', 'height', 'size', 'color', 'fill'];
export const CONTRAST_MIN = 70;                  // 明暗差の目安（§3.2。これより小さいと印を付ける。選ぶのは止めない）
const MIN_SIZE = EMU_PER_IN / 10;                // 枠の幅・高さの下限（0.1インチ）
const ROUNDRECT_TEXT = 0.29289;                  // 角丸四角の文字の領域が角から入る割合（1 − 1/√2）

/** 0.01インチの格子へ（修正票に書く値と、画面で見ている値をそろえる） */
export const snapGrid = (emu) => Math.round(emu / STEP) * STEP;
export const toIn = (emu) => Math.round(emu / STEP) / 100;
export const fromIn = (inch) => Math.round(inch * 100) * STEP;

const COLOR = /^#[0-9A-F]{6}$/;
const upper = (c) => (typeof c === 'string' ? c.toUpperCase() : c);

/** 枠の色（§3.2）: 文字のある段落の色。words＝その枠の overlays（段落 → 行）。無ければ全段落を見る。
 *  空の段落は数えない（テーマの色に落ちていることがあり、何も描かない）。文字のある段落で色が割れていれば null（色は直せない） */
export function boxColor(box, words) {
  const has = (k) => !words || (words[k] || []).some((line) => line.trim() !== '');
  let ps = box.paragraphs.filter((_, k) => has(k));
  if (!ps.length) ps = box.paragraphs;
  const cs = new Set(ps.map((p) => upper(p.color)));
  return cs.size === 1 ? [...cs][0] : null;
}

/** 1つの枠の「直せる値」（EMU と pt・色）。大きさは枠の全段落にそろっている（全作品の実測で、枠の中で大きさが違う枠は0）。
 *  color＝枠の色（直せなければ null）・fill＝下地の色（無ければ null） */
export function editOf(box, words) {
  const sizes = box.paragraphs.map((p) => p.size);
  return {
    x: box.x, y: box.y, width: box.width, height: box.height, size: sizes.length ? Math.max(...sizes) : 18,
    color: boxColor(box, words), fill: box.fill ? upper(box.fill) : null,
  };
}

/** 直した値を枠に当てる（大きさ・色は全段落に効く。fill が null なら下地を消す——文字列 'none' は残さない） */
export function applyEdit(box, e) {
  if (!e) return box;
  const out = {
    ...box, x: e.x, y: e.y, width: e.width, height: e.height,
    paragraphs: box.paragraphs.map((p) => ({ ...p, size: e.size, ...(e.color ? { color: e.color } : {}) })),
  };
  if (e.fill === undefined) return out;              // 色を持たない値（色の欄の無いころの直し）: 下地はそのまま
  if (e.fill) out.fill = e.fill; else delete out.fill;
  return out;
}

/** 中央への吸い付き: 枠の中心がスライドの中心から tol 以内なら合わせる → { pos, snapped } */
export function snapCenter(pos, len, slideLen, tol) {
  const c = slideLen / 2 - len / 2;
  return Math.abs(pos - c) <= tol ? { pos: c, snapped: true } : { pos, snapped: false };
}

/** ドラッグで動かす（dx, dy は EMU）。0.01インチの格子へ・中央へ吸い付く → { edit, guides: { v, h } } */
export function moveBy(start, dx, dy, slide, tol) {
  const sx = snapCenter(start.x + dx, start.width, slide.width, tol);
  const sy = snapCenter(start.y + dy, start.height, slide.height, tol);
  return {
    edit: { ...start, x: sx.snapped ? sx.pos : snapGrid(sx.pos), y: sy.snapped ? sy.pos : snapGrid(sy.pos) },
    guides: { v: sx.snapped, h: sy.snapped },
  };
}

/** 四隅のつまみで大きさを変える。corner: 'nw' | 'ne' | 'sw' | 'se'（つかんだ角が動き、向かいの角は動かない） */
export function resizeBy(start, corner, dx, dy) {
  let { x, y, width, height } = start;
  const right = x + width, bottom = y + height;
  if (corner.includes('w')) { x = Math.min(snapGrid(x + dx), right - MIN_SIZE); width = right - x; }
  else width = Math.max(MIN_SIZE, snapGrid(right + dx) - x);
  if (corner.includes('n')) { y = Math.min(snapGrid(y + dy), bottom - MIN_SIZE); height = bottom - y; }
  else height = Math.max(MIN_SIZE, snapGrid(bottom + dy) - y);
  return { ...start, x, y, width, height };
}

/** 矢印キー（key は 'ArrowLeft' など）。shift＝0.1インチ */
export function nudge(e, key, shift) {
  const d = shift ? BIG_STEP : STEP;
  const m = { ArrowLeft: [-d, 0], ArrowRight: [d, 0], ArrowUp: [0, -d], ArrowDown: [0, d] }[key];
  return m ? { ...e, x: e.x + m[0], y: e.y + m[1] } : e;
}

/** 文字の大きさ（1pt 刻み・1pt 以上） */
export const resize = (e, delta) => ({ ...e, size: Math.max(1, Math.round(e.size) + delta) });

// ---------- 修正票の件（§6 の layout） ----------

/** 値 → 修正票に書く形（インチ小数2桁・整数 pt・大文字の色・下地なしは 'none'）。
 *  fill none と「fill が無い」の読み替えはここだけで行う（差分・判定・当てる、はすべてここを通る）。
 *  枠の色が無い（文字のある段落で割れている）ときは color を持たない */
export function sheetValues(e) {
  const v = { left: toIn(e.x), top: toIn(e.y), width: toIn(e.width), height: toIn(e.height), size: Math.round(e.size) };
  if (e.color) v.color = upper(e.color);
  if (e.fill !== undefined) v.fill = e.fill ? upper(e.fill) : 'none';
  return v;
}

/** 1つの枠の直す前 → 直した後 → 件（変わった値だけ。変わっていなければ null）。words＝その枠の overlays（枠の色を決める） */
export function diffLayout(slide, at, beforeBox, after, words) {
  const b = sheetValues(editOf(beforeBox, words)), a = sheetValues(after);
  const keys = KEYS.filter((k) => a[k] !== undefined && a[k] !== b[k]);   // 直した後に無い値（色の無い枠の color）は比べない
  if (!keys.length) return null;
  const pick = (v) => Object.fromEntries(keys.map((k) => [k, v[k]]));
  return { slide, kind: 'layout', at, before: pick(b), after: pick(a) };
}

/** 件の値 → Markdown の行（left・top・width・height・size・color・fill の順） */
export function layoutLines(values) {
  const line = (k) => (k === 'size' ? `size ${values[k]}pt`
    : k === 'color' || k === 'fill' ? `${k} ${values[k]}` : `${k} ${Number(values[k]).toFixed(2)}in`);
  return KEYS.filter((k) => values[k] !== undefined).map(line).join('\n');
}

/** layout の件を、読み直した作品の同じ枠と比べる → 'done' | 'reworded' | 'pending'（§6 の表） */
export function judgeLayout(item, slideData) {
  const box = (slideData.overlay_layout || [])[item.at - 1];
  if (!box) return 'reworded';
  const now = sheetValues(editOf(box, (slideData.overlays || [])[item.at - 1]));
  const keys = Object.keys(item.after);
  if (keys.every((k) => now[k] === item.after[k])) return 'done';
  if (keys.every((k) => now[k] === item.before[k])) return 'pending';
  return 'reworded';
}

/** layout の件を、いまの作品の枠に当てる。元の値のままの枠にだけ当てる → 直した値（EMU・pt・色）または null。words＝その枠の overlays */
export function applyLayoutItem(item, box, words) {
  const e = editOf(box, words);
  const now = sheetValues(e);
  if (!Object.keys(item.before).every((k) => now[k] === item.before[k])) return null;
  const v = item.after;
  return {
    x: v.left !== undefined ? fromIn(v.left) : e.x, y: v.top !== undefined ? fromIn(v.top) : e.y,
    width: v.width !== undefined ? fromIn(v.width) : e.width, height: v.height !== undefined ? fromIn(v.height) : e.height,
    size: v.size !== undefined ? v.size : e.size,
    color: v.color !== undefined ? v.color : e.color,
    fill: v.fill !== undefined ? (v.fill === 'none' ? null : v.fill) : e.fill,
  };
}

/** 修正票の件の値か（ブラウザの中に保存した票を読むとき）。値の種類ごとに型を見る——数値だけを通すと、色の件が読み直しで黙って消える */
const isValue = (k, x) => (k === 'color' ? typeof x === 'string' && COLOR.test(x)
  : k === 'fill' ? typeof x === 'string' && (x === 'none' || COLOR.test(x))
  : KEYS.includes(k) && typeof x === 'number' && Number.isFinite(x));
export const isLayoutValues = (v) => !!v && typeof v === 'object' && Object.keys(v).length > 0
  && Object.entries(v).every(([k, x]) => isValue(k, x));

/** 色見本: その作品の枠で使っている色（文字の色と下地の色。よく使う順）＋白・黒。
 *  汎用の色は出さない——作品の定数に無い「近いけれど違う色」が書き戻しに入る（プランの決定1） */
export function workPalette(work, max = 14) {
  const count = new Map();
  const add = (c) => { if (c) count.set(c, (count.get(c) || 0) + 1); };
  for (const s of (work && work.slides) || []) {
    (s.overlay_layout || []).forEach((box, i) => {
      add(boxColor(box, (s.overlays || [])[i]));
      add(box.fill ? upper(box.fill) : null);
    });
  }
  const used = [...count.entries()].sort((a, b) => b[1] - a[1]).map(([c]) => c);
  const out = used.filter((c) => c !== '#FFFFFF' && c !== '#000000').slice(0, Math.max(0, max - 2));
  return [...out, '#FFFFFF', '#000000'];
}

// ---------- 明暗差の目安（work-format §3.2 の Light against dark） ----------

/** 色の明るさ（0–255。0.299R + 0.587G + 0.114B） */
export function luma(hex) {
  const n = parseInt(String(hex).slice(1), 16);
  return 0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255);
}

/** 画素の並び（RGBA。canvas の getImageData の data）の明るさの平均 */
export function meanLuma(data) {
  const n = Math.floor(data.length / 4);
  let sum = 0;
  for (let i = 0; i < n * 4; i += 4) sum += 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
  return n ? sum / n : NaN;
}

/** 明暗差 → { gap, low } または null（枠の色が無い・背景が測れない）。
 *  e＝直せる値（editOf の形）。bgLuma＝下敷きの枠の中の明るさの平均（下地のある枠では下地の色を使う） */
export function contrast(e, bgLuma) {
  if (!e.color) return null;
  const bg = e.fill ? luma(e.fill) : bgLuma;
  if (typeof bg !== 'number' || !Number.isFinite(bg)) return null;
  const gap = Math.abs(bg - luma(e.color));
  return { gap, low: gap < CONTRAST_MIN };
}

// ---------- 描き方（work-format §3.2 の Drawing） ----------

/** 枠の描き方（px）。scale＝画面の px / EMU。words＝段落の並び（段落ごとに行の並び）。
 *  戻り値: { box: CSS の値, paragraphs: [{ css, lines }] }——DOM を作るのは呼ぶ側 */
export function drawBox(box, words, scale) {
  const px = (emu) => emu * scale;
  let [l, t, r, b] = box.inset;
  if (box.shape === 'roundRect') {
    const e = (box.corner || 0) * Math.min(box.width, box.height) * ROUNDRECT_TEXT;
    l += e; t += e; r += e; b += e;
  }
  const css = {
    left: `${px(box.x)}px`, top: `${px(box.y)}px`, width: `${px(box.width)}px`, height: `${px(box.height)}px`,
    padding: `${px(t)}px ${px(r)}px ${px(b)}px ${px(l)}px`,
    justifyContent: { top: 'flex-start', middle: 'center', bottom: 'flex-end' }[box.anchor] || 'flex-start',
  };
  if (box.fill) css.background = box.fill;
  if (box.outline) { css.outline = `${px(box.outline.width)}px solid ${box.outline.color}`; css.outlineOffset = `${-px(box.outline.width) / 2}px`; }
  if (box.shape === 'roundRect') css.borderRadius = `${px((box.corner || 0) * Math.min(box.width, box.height))}px`;
  if (box.rotation) css.transform = `rotate(${box.rotation}deg)`;
  const last = box.paragraphs[box.paragraphs.length - 1];
  const paragraphs = (words || []).map((lines, k) => {
    const p = box.paragraphs[k] || last;                 // 段落を足した欄は、最後の段落の書式で描く
    const pcss = {
      textAlign: p.align, fontSize: `${px(p.size * EMU_PER_PT)}px`, fontWeight: p.bold ? '700' : '400',
      color: p.color, fontFamily: `"${p.font}"`, whiteSpace: box.wrap ? 'pre-wrap' : 'pre',
    };
    if (k && p.space_before) pcss.marginTop = `${px(p.space_before * EMU_PER_PT)}px`;
    // 空の段落も1行ぶんの高さ（幅0の文字を置く）
    return { css: pcss, lines: lines.length && lines.some((x) => x !== '') ? lines : ['​'] };
  });
  return { box: css, paragraphs };
}
