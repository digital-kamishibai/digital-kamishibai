// script.md の答え合わせ（tests/golden/）: プレイヤーの読み手（player/js/script.js）が、ビルダーと同じ答えを出す。
// 答えはビルダーで作る（python tests/golden/golden.py）。この読み手だけ違う答えの組は <名前>.js.json
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { readScript } from '../../player/js/script.js';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const HERE = path.join(ROOT, 'tests', 'golden', 'script');
// 見本の台本（tests/golden/golden.py の SOURCES と同じ）
const SOURCES = {
  'sample-story': 'examples/sample-story/script.md',
  'sample-six-friends-smoothie-ja': 'examples/six-friends-smoothie/ja/script.md',
  'sample-six-friends-smoothie-en': 'examples/six-friends-smoothie/en/script.md',
};
const cases = Object.fromEntries([
  ...readdirSync(HERE).filter((f) => f.endsWith('.md')).map((f) => [f.slice(0, -3), path.join(HERE, f)]),
  ...Object.entries(SOURCES).map(([k, p]) => [k, path.join(ROOT, p)]),
]);

// 見本の答えは台本の文を含まない形（tests/golden/golden.py の digest と同じ）: キーを並べ、空白なしの JSON の SHA-256
const sorted = (x) => (Array.isArray(x) ? x.map(sorted)
  : x && typeof x === 'object' ? Object.fromEntries(Object.keys(x).sort().map((k) => [k, sorted(x[k])])) : x);
const digest = (a) => ({
  digest: createHash('sha256').update(JSON.stringify(sorted(a)), 'utf8').digest('hex'),
  slides: a.work ? a.work.slides.length : null, errors: a.errors, warnings: a.warnings,
});

const read = (file) => {
  const r = readScript(readFileSync(file, 'utf8'));
  return JSON.parse(JSON.stringify({ work: r.work, texts: r.texts, errors: r.errorCodes, warnings: r.warningCodes }));
};

test('答え合わせの組がある', () => {
  assert.ok(Object.keys(cases).length >= 10);
});

for (const [name, file] of Object.entries(cases)) {
  test(`${name}: ビルダーと同じに読む`, () => {
    const js = path.join(HERE, `${name}.js.json`);
    const want = JSON.parse(readFileSync(existsSync(js) ? js : path.join(HERE, `${name}.json`), 'utf8'));
    const got = read(file);
    assert.deepEqual(name in SOURCES ? digest(got) : got, want);
  });
}

test('文言もビルダーと同じ形（場所: 文）', () => {
  const r = readScript('# T\n\n## [Slide 1] A\n\n> [Bild] x.jpg\n');
  assert.equal(r.errors[0].startsWith('line 5: unknown cue "[Bild]"'), true, r.errors[0]);
  assert.deepEqual(r.errorCodes, ['cue-unknown line 5']);
});
