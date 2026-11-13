// サイトの見本を開く（docs/work-format.md §1「Samples on the site」）。純粋な関数だけ（node --test で守る）。
// 見本の一覧 sample-list.json と版の目録 samples/<slug>/<lang>/<版>/version.json は、scripts/fetch-samples.mjs が配る直前に作る。

export const SAMPLE_LIST = 'sample-list.json';
const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const LANG = /^[a-z]{2,3}(?:-[A-Za-z0-9]+)*$/;
const PATH = /^[A-Za-z0-9_][A-Za-z0-9_./-]*$/;

/** ページの URL の ?sample=<slug>&lang=<lang>&variant=1。無い・形が変なら null（lang は無くてよい）。
 *  variant＝このブラウザに置いた、語りを変えた版で開く（段2） */
export function sampleQuery(search) {
  const q = new URLSearchParams(search);
  const slug = q.get('sample');
  if (!slug || !SLUG.test(slug)) return null;
  const lang = q.get('lang');
  return { slug, lang: lang && LANG.test(lang) ? lang : null, variant: q.get('variant') === '1' };
}

/** 一覧から開く見本を選ぶ: 書かれた言語 → 端末の言語 → 英語 → その見本の最初の言語。無ければ null */
export function pickSample(list, slug, lang, deviceLang = '') {
  const same = (Array.isArray(list) ? list : []).filter((e) => e && e.slug === slug && LANG.test(e.lang ?? '') && Number.isInteger(e.version) && e.version > 0);
  const dev = String(deviceLang).toLowerCase().split('-')[0];
  return same.find((e) => e.lang === lang) || same.find((e) => e.lang === dev) || same.find((e) => e.lang === 'en') || same[0] || null;
}

/** その版の置き場（サイトの中の道。末尾に /） */
export function sampleBase(e) {
  return `samples/${e.slug}/${e.lang}/${e.version}/`;
}

export function isSafePath(p) {
  return typeof p === 'string' && p.length <= 200 && PATH.test(p) && p.split('/').every((s) => s && s !== '.' && s !== '..');
}

/** 版の目録（version.json）から、取ってくる素材（台本・手引き・絵のプロンプトを除く）と BGM の大きさ。形が変なら投げる */
export function sampleFiles(v) {
  if (!v || !Array.isArray(v.files)) throw new Error('version.json: files is missing');
  const files = v.files.filter((f) => !['work.json', 'script.md', 'holes.md', 'plan.md'].includes(f.path));
  for (const f of files) {
    if (!isSafePath(f.path) || !Number.isInteger(f.size) || f.size < 0) throw new Error(`version.json: bad file ${JSON.stringify(f)}`);
  }
  const levels = {};
  for (const [p, l] of Object.entries(v.levels || {})) if (typeof l === 'number' && Number.isFinite(l)) levels[p] = l;
  return { files, total: files.reduce((a, f) => a + f.size, 0), levels };
}

/** 聞き手が受けてよい「サイトの中の道」か（同じサイトの samples/ の下だけ。外の URL や .. は通さない） */
export function isSiteSrc(src) {
  if (typeof src !== 'string') return false;
  const m = /^samples\/([^/]+)\/([^/]+)\/(\d+)\/(.+)$/.exec(src);
  return !!m && SLUG.test(m[1]) && LANG.test(m[2]) && isSafePath(m[4]);
}

/** 玄関のカード: 見本ごとに1枚、端末の言語の版（無ければ英語・最初の言語）。一覧の順のまま */
export function cardsFor(list, deviceLang = '') {
  const slugs = [...new Set((Array.isArray(list) ? list : []).filter((e) => e && SLUG.test(e.slug ?? '')).map((e) => e.slug))];
  return slugs.map((slug) => pickSample(list, slug, null, deviceLang)).filter(Boolean)
    .map((e) => ({ ...e, href: `narrator.html?sample=${encodeURIComponent(e.slug)}&lang=${encodeURIComponent(e.lang)}` }));
}
