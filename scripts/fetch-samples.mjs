// サイトの見本を取り込む（配る直前に1回）: node scripts/fetch-samples.mjs
// examples/<slug>/<lang>/site.json の全部の版を、Release `site-media` から取り、SHA-256 を確かめて
// player/samples/<slug>/<lang>/<version>/… に置く（語り手が読む版の目録 version.json も）。見本の一覧は player/sample-list.json。
// 1つでも合わなければ何も置かずに止まる（配らない）。Node の標準だけで動く（Workers Builds・Actions の箱でも）。
// 取ったものは .cache/site-media/ に残し、2回目からは取らない。
// DK_SITE_MEDIA を置くと、Release の代わりにそのフォルダから取る（テスト用）。

import { mkdir, readdir, readFile, rm, writeFile, rename } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { MEDIA_BASE, assetName, isText, latest, normalizeText, sha256, validateSite } from './sites.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const EXAMPLES = path.join(ROOT, 'examples');
const CACHE = path.join(ROOT, '.cache', 'site-media');
const OUT = path.join(ROOT, 'player', 'samples');
const LIST = path.join(ROOT, 'player', 'sample-list.json');
const LOCAL = process.env.DK_SITE_MEDIA;

async function findSites() {
  const sites = [];
  for (const slug of (await readdir(EXAMPLES, { withFileTypes: true })).filter((d) => d.isDirectory())) {
    for (const lang of (await readdir(path.join(EXAMPLES, slug.name), { withFileTypes: true })).filter((d) => d.isDirectory())) {
      const p = path.join(EXAMPLES, slug.name, lang.name, 'site.json');
      if (existsSync(p)) sites.push({ slug: slug.name, lang: lang.name, file: p });
    }
  }
  return sites;
}

/** 資産を1つ取る（手元の写しが合えばそれ）。中身が目録と合わなければ投げる */
async function asset(f) {
  const name = assetName(f);
  const cached = path.join(CACHE, name);
  if (existsSync(cached)) {
    const buf = await readFile(cached);
    if (buf.length === f.size && sha256(buf) === f.sha256) return buf;
  }
  let buf;
  if (LOCAL) buf = await readFile(path.join(LOCAL, name));
  else {
    const res = await fetch(MEDIA_BASE + name);
    if (!res.ok) throw new Error(`${f.path}: ${MEDIA_BASE + name}: HTTP ${res.status}`);
    buf = Buffer.from(await res.arrayBuffer());
  }
  const got = isText(f.path) ? normalizeText(buf) : buf;
  if (got.length !== f.size || sha256(got) !== f.sha256) throw new Error(`${f.path}: ${name} does not match site.json (size or SHA-256)`);
  await mkdir(CACHE, { recursive: true });
  await writeFile(cached, got);
  return got;
}

async function main() {
  const sites = await findSites();
  const staged = OUT + '.new';
  await rm(staged, { recursive: true, force: true });
  const list = [];
  for (const s of sites) {
    const site = JSON.parse(await readFile(s.file, 'utf8'));
    const errors = validateSite(site, s.slug, s.lang);
    if (errors.length) throw new Error(`${path.relative(ROOT, s.file)}:\n  ${errors.join('\n  ')}`);
    for (const v of site.versions) {
      for (const f of v.files) {
        const dest = path.join(staged, s.slug, s.lang, String(v.version), ...f.path.split('/'));
        await mkdir(path.dirname(dest), { recursive: true });
        await writeFile(dest, await asset(f));
      }
      // 語り手が読む版の目録（進み具合のための大きさと、BGM の大きさ）。SHA-256 は要らない（ここで確かめ済み）
      const files = v.files.map((f) => ({ path: f.path, size: f.size }));
      await writeFile(path.join(staged, s.slug, s.lang, String(v.version), 'version.json'),
        JSON.stringify({ version: v.version, files, levels: v.levels ?? {} }));
    }
    const v = latest(site);
    const work = JSON.parse(await readFile(path.join(staged, s.slug, s.lang, String(v.version), 'work.json'), 'utf8'));
    list.push({ slug: s.slug, lang: s.lang, version: v.version, title: work.title, line: site.card?.line ?? '' });
    console.log(`${s.slug}/${s.lang}: ${site.versions.length} version(s), newest ${v.version}`);
  }
  // 全部そろってから入れ替える（途中で止まったら、前の写しのまま）
  await rm(OUT, { recursive: true, force: true });
  if (sites.length) await rename(staged, OUT);
  await writeFile(LIST, JSON.stringify(list, null, 2) + '\n');
  console.log(`samples: ${list.length}`);
}

main().catch((e) => {
  console.error(`fetch-samples: ${e.message}`);
  process.exit(1);
});
