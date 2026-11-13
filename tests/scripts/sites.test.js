// サイトの見本の目録（scripts/sites.mjs）と、git の見本との食い違い
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { assetName, isSafePath, latest, normalizeText, sha256, validateSite, MAX_FILE } from '../../scripts/sites.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const SHA = 'a'.repeat(64);
const file = (p, extra = {}) => ({ path: p, size: 10, sha256: SHA, ...extra });
const site = (versions) => ({ card: { line: 'x' }, versions });

test('isSafePath: 見本の中の相対パスだけを通す', () => {
  for (const ok of ['work.json', 'pictures/_built/01.jpg', 'sounds/bgm.mp3']) assert.ok(isSafePath(ok), ok);
  for (const bad of ['', '/etc/passwd', '../x', 'a/../b', 'a//b', 'a\\b', 'C:/x', './a', 'a/', 'ü.jpg', 'a b.jpg', '.hidden']) {
    assert.ok(!isSafePath(bad), bad);
  }
});

test('assetName: 中身の SHA-256＋拡張子（小文字）', () => {
  assert.equal(assetName(file('videos/Ending.MP4')), SHA + '.mp4');
  assert.equal(assetName(file('pictures/_built/01.jpg')), SHA + '.jpg');
});

test('normalizeText: CRLF を LF に', () => {
  assert.equal(normalizeText(Buffer.from('a\r\nb\n')).toString(), 'a\nb\n');
});

test('validateSite: 正しい目録', () => {
  const s = site([{ version: 1, files: [file('work.json'), file('sounds/bgm.mp3')], levels: { 'sounds/bgm.mp3': -31.7 } }]);
  assert.deepEqual(validateSite(s, 'six-friends-smoothie', 'ja'), []);
  assert.equal(latest(s).version, 1);
});

test('validateSite: 版は1から1つずつ増える', () => {
  const v = (n) => ({ version: n, files: [file('work.json')] });
  assert.deepEqual(validateSite(site([v(1), v(2)]), 's', 'en'), []);
  assert.ok(validateSite(site([v(1), v(3)]), 's', 'en').some((e) => e.includes('version 2')));
  assert.ok(validateSite(site([v(2)]), 's', 'en').length);
  assert.ok(validateSite(site([]), 's', 'en').length);
});

test('validateSite: 取り違え・大きすぎ・危ないパスを止める', () => {
  const bad = (files, levels) => validateSite(site([{ version: 1, files, levels }]), 's', 'en');
  assert.ok(bad([file('sounds/bgm.mp3')]).some((e) => e.includes('work.json is missing')));
  assert.ok(bad([file('work.json'), file('../x.mp3')]).some((e) => e.includes('bad path')));
  assert.ok(bad([file('work.json'), file('work.json')]).some((e) => e.includes('twice')));
  assert.ok(bad([file('work.json', { sha256: 'xyz' })]).some((e) => e.includes('sha256')));
  assert.ok(bad([file('work.json', { size: MAX_FILE + 1 })]).some((e) => e.includes('25 MiB')));
  assert.ok(bad([file('work.json')], { 'sounds/bgm.mp3': -30 }).some((e) => e.includes('not in files')));
  assert.ok(bad([file('work.json'), file('a.mp3')], { 'a.mp3': 3 }).some((e) => e.includes('LUFS')));
  assert.ok(validateSite(site([{ version: 1, files: [file('work.json')] }]), 'Bad_Slug', 'en').length);
});

// git の見本を直したのに目録を作り直していない、を見つける（直したら python scripts/site_media.py を回して版を上げる）
const sites = readdirSync(path.join(ROOT, 'examples'), { withFileTypes: true })
  .filter((d) => d.isDirectory())
  .flatMap((d) => readdirSync(path.join(ROOT, 'examples', d.name), { withFileTypes: true })
    .filter((l) => l.isDirectory() && existsSync(path.join(ROOT, 'examples', d.name, l.name, 'site.json')))
    .map((l) => ({ slug: d.name, lang: l.name, dir: path.join(ROOT, 'examples', d.name, l.name) })));

test('site.json のある見本がある', () => {
  assert.ok(sites.some((s) => s.slug === 'six-friends-smoothie' && s.lang === 'ja'));
  assert.ok(sites.some((s) => s.slug === 'six-friends-smoothie' && s.lang === 'en'));
});

for (const s of sites) {
  test(`${s.slug}/${s.lang}: 目録が正しく、一番新しい版の台本が examples と同じ`, () => {
    const json = JSON.parse(readFileSync(path.join(s.dir, 'site.json'), 'utf8'));
    assert.deepEqual(validateSite(json, s.slug, s.lang), []);
    assert.ok(json.card.line, 'card.line（玄関のカードの1行）');
    const v = latest(json);
    for (const name of ['work.json', 'script.md']) {
      const f = v.files.find((x) => x.path === name);
      assert.ok(f, name);
      assert.equal(sha256(normalizeText(readFileSync(path.join(s.dir, name)))), f.sha256,
        `${name} は目録の版 ${v.version} と違う（python scripts/site_media.py で版を上げる）`);
    }
    // work.json が指す絵・音・動画が、全部目録にある
    const work = JSON.parse(readFileSync(path.join(s.dir, 'work.json'), 'utf8'));
    const listed = new Set(v.files.map((x) => x.path));
    for (const sl of work.slides) {
      if (sl.picture) assert.ok(listed.has(sl.picture), sl.picture);
      for (const c of sl.cues) if (c.file) assert.ok(listed.has(c.file), c.file);
    }
  });
}
