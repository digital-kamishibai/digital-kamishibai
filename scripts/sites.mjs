// サイトの見本の目録（examples/<slug>/<lang>/site.json）を読む純粋な関数。定義は docs/work-format.md §1「Samples on the site」。
// 取り込み（fetch-samples.mjs）とテストが使う。ファイルにも通信にも触らない。

import { createHash } from 'node:crypto';

/** 素材の置き場（公開用リポジトリの Release `site-media`）。資産の名前は中身の SHA-256＋拡張子 */
export const MEDIA_BASE = 'https://github.com/digital-kamishibai/digital-kamishibai/releases/download/site-media/';
/** 静的ファイルの1ファイルの上限（Workers の静的ファイル） */
export const MAX_FILE = 25 * 1024 * 1024;

const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const LANG = /^[a-z]{2,3}(?:-[A-Za-z0-9]+)*$/;
const SHA = /^[0-9a-f]{64}$/;
const EXT = /\.[a-z0-9]{1,5}$/;

/** 見本の中の相対パスとして受けてよいか（.. や絶対パス、`\`、変わった字を通さない） */
export function isSafePath(p) {
  if (typeof p !== 'string' || !p || p.length > 200) return false;
  if (!/^[A-Za-z0-9_][A-Za-z0-9_./-]*$/.test(p)) return false;
  return p.split('/').every((seg) => seg && seg !== '.' && seg !== '..');
}

/** Release の資産の名前 */
export function assetName(file) {
  const m = file.path.toLowerCase().match(EXT);
  return file.sha256 + (m ? m[0] : '');
}

/** 文字のファイル（work.json・script.md）は改行を LF にそろえて量る（Windows の写しは CRLF になる） */
export function isText(path) {
  return /\.(json|md)$/i.test(path);
}

export function normalizeText(buf) {
  return Buffer.from(buf.toString('utf8').replace(/\r\n/g, '\n'), 'utf8');
}

export function sha256(buf) {
  return createHash('sha256').update(buf).digest('hex');
}

/** site.json を検査する。errors が空なら使ってよい。slug・lang はフォルダの名前から */
export function validateSite(json, slug, lang) {
  const errors = [];
  if (!SLUG.test(slug)) errors.push(`slug is not a-z, 0-9 and -: ${slug}`);
  if (!LANG.test(lang)) errors.push(`lang is not a language code: ${lang}`);
  if (!json || typeof json !== 'object') return [...errors, 'site.json is not a JSON object'];
  if (json.card !== undefined && (typeof json.card !== 'object' || typeof json.card.line !== 'string')) {
    errors.push('card must be {"line": "..."}');
  }
  if (!Array.isArray(json.versions) || json.versions.length === 0) return [...errors, 'versions must have at least one version'];
  json.versions.forEach((v, i) => {
    const where = `version ${i + 1}`;
    if (!v || v.version !== i + 1) errors.push(`${where}: version must be ${i + 1} (versions only ever grow, by one)`);
    if (!Array.isArray(v?.files) || v.files.length === 0) {
      errors.push(`${where}: files must not be empty`);
      return;
    }
    const seen = new Set();
    for (const f of v.files) {
      if (!f || !isSafePath(f.path)) { errors.push(`${where}: bad path ${JSON.stringify(f?.path)}`); continue; }
      if (seen.has(f.path)) errors.push(`${where}: ${f.path} twice`);
      seen.add(f.path);
      if (!SHA.test(f.sha256 ?? '')) errors.push(`${where}: ${f.path}: sha256 must be 64 hex digits`);
      if (!Number.isInteger(f.size) || f.size <= 0) errors.push(`${where}: ${f.path}: size must be a whole number of bytes`);
      else if (f.size > MAX_FILE) errors.push(`${where}: ${f.path}: over 25 MiB (${f.size} bytes)`);
    }
    if (!seen.has('work.json')) errors.push(`${where}: work.json is missing`);
    if (v.levels !== undefined) {
      if (!v.levels || typeof v.levels !== 'object') errors.push(`${where}: levels must be {path: LUFS}`);
      else for (const [p, l] of Object.entries(v.levels)) {
        if (!seen.has(p)) errors.push(`${where}: levels: ${p} is not in files`);
        if (typeof l !== 'number' || !Number.isFinite(l) || l > 0 || l < -70) errors.push(`${where}: levels: ${p} must be LUFS (-70 to 0)`);
      }
    }
  });
  return errors;
}

/** 一番新しい版 */
export function latest(site) {
  return site.versions[site.versions.length - 1];
}
