// 配った見本の「語りを少し変えた版」（docs/work-format.md §6 の最後）。純粋な関数だけ（node --test で守る）。
// 替えられるのは黄色い所（穴の語り）だけ。変えた版は script.md そのもの: 見本の script.md の、印の付いた行の連なりを差し替え、
// 見出しに Based on・Changed を入れたもの。ほかの行は一字も変えない。
// 見本を元に書いた台本（§6「A script written from a sample」、段4a）: 語りはどこが替わってもよく、骨組み（絵・合図・画面の文字）が
// 見本と同じときだけ見本の素材で開く。

const HEADING = /^## \[Slide ([0-9]+)\]/;
const MARK = /^~([0-9]*) /;
const BASED_ON = /^>[ \t]*Based on:/;
const CHANGED = /^>[ \t]*Changed:/;
const LANGUAGE = /^>[ \t]*Language:/;
const TITLE = /^# /;
export const CREDIT = 'Digital Kamishibai, by Fast Focus Technologies, CC BY 4.0, https://digitalkamishibai.org';

const linesOf = (script) => String(script).replace(/^﻿+/, '').replace(/\r\n?/g, '\n').split('\n');

/** 替えられる欄: 1枚の中で、同じ印の行が続いている所（空行・印の違う行・印の無い行で切れる）。
 *  戻り値: [{ index, slide, hole（穴の番号。無ければ ''）, start, end（行の番号、end は含まない）, text（印を外した文） }] */
export function holeRuns(script) {
  const lines = linesOf(script);
  const runs = [];
  let slide = 0;
  let ended = false;          // その枚の "---" より後（読まれない）
  let cur = null;
  const close = () => { if (cur) { runs.push(cur); cur = null; } };
  lines.forEach((line, i) => {
    const h = HEADING.exec(line);
    if (h) { close(); slide = Number(h[1]); ended = false; return; }
    if (!slide || ended) return;
    if (line === '---') { close(); ended = true; return; }
    const m = MARK.exec(line);
    if (!m) { close(); return; }
    if (cur && cur.hole === m[1] && cur.end === i) {
      cur.end = i + 1;
      cur.lines.push(line.slice(m[0].length));
      return;
    }
    close();
    cur = { slide, hole: m[1], start: i, end: i + 1, lines: [line.slice(m[0].length)] };
  });
  close();
  return runs.map((r, index) => ({ index, slide: r.slide, hole: r.hole, start: r.start, end: r.end, text: r.lines.join('\n') }));
}

/** 欄の文を差し替えた台本。texts[i] が runs[i] の新しい文（undefined なら変えない）。
 *  行ごとに同じ印を付け直す。欄の中の空行は落とす（欄は「続いた行」なので、空行を入れると段落が分かれて黄色の外が変わる）。
 *  欄が空なら、印だけの行を1つ残す（その穴は語らない。欄の数は変えない） */
export function applyTexts(script, texts) {
  const lines = linesOf(script);
  const runs = holeRuns(script);
  for (const r of [...runs].reverse()) {
    const t = texts[r.index];
    if (t === undefined || t === null) continue;
    const mark = `~${r.hole} `;
    const body = String(t).replace(/\r\n?/g, '\n').split('\n').map((l) => l.replace(/[ \t]+$/, '')).filter((l) => l.trim());
    const out = body.length ? body.map((l) => mark + l) : [mark];
    lines.splice(r.start, r.end - r.start, ...out);
  }
  return lines.join('\n');
}

/** 見本の版と比べて、変わった欄の番号。欄の数が違えば null（見本の黄色い所のほかが変わっている） */
export function changedRuns(sampleScript, script) {
  const a = holeRuns(sampleScript);
  const b = holeRuns(script);
  if (a.length !== b.length || a.some((r, i) => r.slide !== b[i].slide || r.hole !== b[i].hole)) return null;
  return a.filter((r, i) => r.text !== b[i].text).map((r) => r.index);
}

/** 黄色い所と、見出しの Based on・Changed のほかが、見本と一字も同じか */
export function sameOutsideHoles(sampleScript, script) {
  const strip = (s) => {
    const lines = linesOf(s);
    const drop = new Set();
    for (const r of holeRuns(s)) for (let i = r.start; i < r.end; i++) drop.add(i);
    return lines.filter((l, i) => !drop.has(i) && !BASED_ON.test(l) && !CHANGED.test(l)).join('\n');
  };
  return strip(sampleScript) === strip(script);
}

/** Changed の行の中身（人が読む）: 穴ごとに、乗っている枚 */
export function changedSummary(runs, indexes, lang = 'en') {
  const byHole = new Map();
  for (const i of indexes) {
    const r = runs[i];
    if (!r) continue;
    if (!byHole.has(r.hole)) byHole.set(r.hole, new Set());
    byHole.get(r.hole).add(r.slide);
  }
  const ja = String(lang).toLowerCase().startsWith('ja');
  const parts = [...byHole.entries()].sort((x, y) => Number(x[0] || 1e9) - Number(y[0] || 1e9)).map(([hole, slides]) => {
    const s = [...slides].sort((a, b) => a - b);
    if (ja) return `${hole ? `穴${hole}` : '黄色い語り'}（${s.join('・')}枚目）`;
    return `${hole ? `hole ${hole}` : 'highlighted narration'} (slide${s.length > 1 ? 's' : ''} ${s.join(', ')})`;
  });
  return parts.join(ja ? '、' : '; ');
}

/** 見出しに Based on・Changed を入れる（前にあれば置き換える）。> Language: の次（無ければ題の次） */
export function withHeader(script, { title, slug, lang, version }, changed) {
  const lines = linesOf(script).filter((l, i, all) => {
    const first = all.findIndex((x) => HEADING.test(x));
    return !(i < (first < 0 ? all.length : first) && (BASED_ON.test(l) || CHANGED.test(l)));
  });
  const first = lines.findIndex((x) => HEADING.test(x));
  const header = first < 0 ? lines.length : first;
  let at = lines.slice(0, header).findIndex((l) => LANGUAGE.test(l));
  if (at < 0) at = lines.slice(0, header).findIndex((l) => TITLE.test(l));
  const add = [`> Based on: ${title} (${slug}/${lang}, version ${version}) — ${CREDIT}`];
  if (changed) add.push(`> Changed: ${changed}`);
  lines.splice(at + 1, 0, ...add);
  return lines.join('\n');
}

/** 見出しの Based on から { slug, lang, version }。無ければ null */
export function basedOn(script) {
  const lines = linesOf(script);
  const first = lines.findIndex((x) => HEADING.test(x));
  for (const l of lines.slice(0, first < 0 ? lines.length : first)) {
    if (!BASED_ON.test(l)) continue;
    const all = [...l.matchAll(/\(([a-z0-9]+(?:-[a-z0-9]+)*)\/([a-z]{2,3}(?:-[A-Za-z0-9]+)*), version ([0-9]+)\)/g)];
    const m = all[all.length - 1];
    if (m) return { slug: m[1], lang: m[2], version: Number(m[3]) };
  }
  return null;
}

/** 見本の版から変えた版を作る（欄の文 → script.md） */
export function makeVariant(sampleScript, texts, meta) {
  const changed = applyTexts(sampleScript, texts);
  const idx = changedRuns(sampleScript, changed) || [];
  return withHeader(changed, meta, changedSummary(holeRuns(sampleScript), idx, meta.lang));
}

/** 骨組み（枚の数、各枚の [Picture]・機械の合図・[Text]）が見本と同じか。読んだ結果で比べる（書き癖で止めない）。
 *  sampleRead・read は readScript の戻り値（work があること。[Text] は最上位の texts）。戻り値: 違う所の一覧（同じなら []）——
 *  { what: 'slides', sample, script } か { what: 'picture' | 'cues' | 'text', slide } */
export function skeletonDiffs(sampleRead, read) {
  const a = sampleRead.work.slides;
  const b = read.work.slides;
  if (a.length !== b.length) return [{ what: 'slides', sample: a.length, script: b.length }];
  const out = [];
  const same = (x, y) => JSON.stringify(x ?? null) === JSON.stringify(y ?? null);
  a.forEach((s, i) => {
    if (!same(s.picture, b[i].picture)) out.push({ what: 'picture', slide: i + 1 });
    if (!same(s.cues, b[i].cues)) out.push({ what: 'cues', slide: i + 1 });
    if (!same((sampleRead.texts || {})[s.number], (read.texts || {})[b[i].number])) out.push({ what: 'text', slide: i + 1 });
  });
  return out;
}

/** Based on の無い台本に合う見本: candidates は [{ entry, read }]（read は見本の script.md を読んだもの）。
 *  骨組みが同じものが1つだけなら { entry }、2つ以上なら { many: [entry…] }、無ければ { none: true, nearest }——
 *  nearest は枚の数が同じで違う所がいちばん少ない見本 { entry, diffs }（AI が1行だけ変えたときに、どこを戻せばよいか言える）。無ければ null */
export function pickBySkeleton(candidates, read) {
  const scored = candidates.filter((c) => c.read.work).map((c) => ({ entry: c.entry, diffs: skeletonDiffs(c.read, read) }));
  const hit = scored.filter((c) => !c.diffs.length).map((c) => c.entry);
  if (hit.length === 1) return { entry: hit[0] };
  if (hit.length) return { many: hit };
  const near = scored.filter((c) => c.diffs[0].what !== 'slides').sort((a, b) => a.diffs.length - b.diffs.length);
  return { none: true, nearest: near.length && (near.length === 1 || near[0].diffs.length < near[1].diffs.length) ? near[0] : null };
}

/** 番号の並びを短く: [1,2,3,5] → 1〜3・5（ja）／1–3, 5（en） */
function spans(nums, ja) {
  const out = [];
  for (const n of nums) {
    const last = out[out.length - 1];
    if (last && n === last[1] + 1) last[1] = n; else out.push([n, n]);
  }
  return out.map(([x, y]) => (x === y ? String(x) : `${x}${ja ? '〜' : '–'}${y}`)).join(ja ? '・' : ', ');
}

/** 見本を元に書いた台本の Changed の中身: 語りが見本と違う枚。sampleRead・read は readScript の戻り値 */
export function narrationSummary(sampleRead, read, lang = 'en') {
  const a = sampleRead.work.slides;
  const nums = read.work.slides.filter((s, i) => !a[i] || a[i].notes !== s.notes).map((s) => s.number);
  if (!nums.length) return '';
  const ja = String(lang).toLowerCase().startsWith('ja');
  if (ja) return `語り（${spans(nums, true)}枚目）`;
  return `narration (slide${nums.length > 1 ? 's' : ''} ${spans(nums, false)})`;
}

/** 見本を元に書いた台本（origin）の黄色い所を欄の文で差し替え、見出しに Based on・Changed（語りの変わった枚）を入れる */
export function makeMade(origin, texts, meta, sampleRead, read) {
  const changed = applyTexts(origin, texts);
  const r = read(changed);
  return withHeader(changed, meta, r.work ? narrationSummary(sampleRead, r, meta.lang) : '');
}

/** 台本の全体が1つのコードブロック（``` や ~~~ の行で始まり、同じ記号の行で終わる）なら、その中身。違えばそのまま。
 *  チャット AI の答えを枠ごと貼ると、記号の行が最後の枚の語りに残るため（前後の空行・枠の外の文は見ない） */
export function unfence(text) {
  const lines = String(text).replace(/\r\n?/g, '\n').split('\n');
  let a = 0;
  let b = lines.length - 1;
  while (a <= b && !lines[a].trim()) a++;
  while (b >= a && !lines[b].trim()) b--;
  const open = a < b ? /^(`{3,}|~{3,})[^`]*$/.exec(lines[a].trim()) : null;
  if (!open || lines[b].trim() !== open[1]) return String(text);
  return lines.slice(a + 1, b).join('\n');
}

/** 行頭の全角の印（「～ 」「〜 」「～1 」など）。貼った台本で数え、直すかを聞く（黙って直さない） */
const WIDE_MARK = /^[～〜]([0-9０-９]*)[ 　]/;
export function wideMarks(script) {
  return linesOf(script).filter((l) => WIDE_MARK.test(l)).length;
}
export function fixWideMarks(script) {
  const digits = (d) => d.replace(/[０-９]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0xFEE0));
  return linesOf(script).map((l) => l.replace(WIDE_MARK, (m, n) => `~${digits(n)} `)).join('\n');
}

/** 画面に出す作品: 見本の work.json の、題・各枚の題・語り（notes）だけを、台本を読んだものに替えたもの。
 *  sampleRead・variantRead は readScript の戻り値。骨組みが見本と違えば { error, diffs } */
export function variantWork(sampleWork, sampleRead, variantRead) {
  if (!variantRead.work) return { error: 'read', detail: variantRead.errors };
  const diffs = skeletonDiffs(sampleRead, variantRead);
  if (diffs.length) return diffs[0].what === 'slides' ? { error: 'slides', diffs } : { error: 'slide', slide: diffs[0].slide, diffs };
  const b = variantRead.work.slides;
  if (sampleWork.slides.length !== b.length) return { error: 'slides', diffs: [] };
  return { work: { ...sampleWork, title: variantRead.work.title || sampleWork.title,
    slides: sampleWork.slides.map((s, i) => ({ ...s, title: b[i].title, notes: b[i].notes })) } };
}
