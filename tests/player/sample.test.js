// サイトの見本を開く（player/js/sample.js）
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { sampleQuery, pickSample, sampleBase, sampleFiles, isSiteSrc, cardsFor } from '../../player/js/sample.js';

test('sampleQuery: ?sample=<slug>&lang=<lang>', () => {
  assert.deepEqual(sampleQuery('?sample=six-friends-smoothie'), { slug: 'six-friends-smoothie', lang: null, variant: false });
  assert.deepEqual(sampleQuery('?sample=six-friends-smoothie&lang=ja'), { slug: 'six-friends-smoothie', lang: 'ja', variant: false });
  assert.deepEqual(sampleQuery('?sample=a&lang=../x'), { slug: 'a', lang: null, variant: false });
  assert.deepEqual(sampleQuery('?sample=a&lang=ja&variant=1'), { slug: 'a', lang: 'ja', variant: true });
  for (const bad of ['', '?test', '?sample=', '?sample=../x', '?sample=A_B', '?sample=a/b']) assert.equal(sampleQuery(bad), null, bad);
});

const LIST = [
  { slug: 's', lang: 'en', version: 1 },
  { slug: 's', lang: 'ja', version: 2 },
  { slug: 'only-fr', lang: 'fr', version: 1 },
];

test('pickSample: 書かれた言語 → 端末の言語 → 英語 → 最初', () => {
  assert.equal(pickSample(LIST, 's', 'ja', 'en-US').lang, 'ja');
  assert.equal(pickSample(LIST, 's', null, 'ja-JP').lang, 'ja');
  assert.equal(pickSample(LIST, 's', null, 'de-DE').lang, 'en');
  assert.equal(pickSample(LIST, 's', 'ko', 'de').lang, 'en');
  assert.equal(pickSample(LIST, 'only-fr', null, 'ja').lang, 'fr');
  assert.equal(pickSample(LIST, 'none', null, 'ja'), null);
  assert.equal(pickSample(null, 's', null, 'ja'), null);
  assert.equal(pickSample([{ slug: 's', lang: 'en', version: '1' }], 's', 'en', 'en'), null, '版が数でない一覧は使わない');
});

test('sampleBase: 版ごとの置き場', () => {
  assert.equal(sampleBase({ slug: 's', lang: 'ja', version: 2 }), 'samples/s/ja/2/');
});

test('sampleFiles: 台本を除いた素材・合計・BGM の大きさ', () => {
  const r = sampleFiles({
    version: 1,
    files: [{ path: 'work.json', size: 5 }, { path: 'script.md', size: 7 }, { path: 'holes.md', size: 9 }, { path: 'plan.md', size: 11 }, { path: 'pictures/_built/01.jpg', size: 100 }, { path: 'sounds/bgm.mp3', size: 900 }],
    levels: { 'sounds/bgm.mp3': -31.7, 'x.mp3': 'loud' },
  });
  assert.deepEqual(r.files.map((f) => f.path), ['pictures/_built/01.jpg', 'sounds/bgm.mp3']);
  assert.equal(r.total, 1000);
  assert.deepEqual(r.levels, { 'sounds/bgm.mp3': -31.7 });
  assert.throws(() => sampleFiles({ files: [{ path: '../secret', size: 1 }] }));
  assert.throws(() => sampleFiles({}));
});

test('isSiteSrc: 同じサイトの samples/ の下だけ', () => {
  assert.ok(isSiteSrc('samples/six-friends-smoothie/ja/1/videos/ending.mp4'));
  for (const bad of [
    'https://example.com/x.mp4', '//example.com/x', '/samples/s/ja/1/a.mp3', 'samples/s/ja/1/../../../x',
    'samples/s/ja/x/a.mp3', 'samples/S/ja/1/a.mp3', 'samples/s/ja/1/', 'videos/ending.mp4', null, 5,
  ]) assert.ok(!isSiteSrc(bad), String(bad));
});

test('cardsFor: 見本ごとに1枚、端末の言語の版', () => {
  const list = [
    { slug: 'b', lang: 'en', version: 1, title: 'B' },
    { slug: 'b', lang: 'ja', version: 1, title: 'ビー' },
    { slug: 'a', lang: 'en', version: 3, title: 'A' },
    { slug: '../x', lang: 'en', version: 1 },
  ];
  assert.deepEqual(cardsFor(list, 'ja-JP').map((c) => [c.slug, c.lang]), [['b', 'ja'], ['a', 'en']]);
  assert.deepEqual(cardsFor(list, 'fr').map((c) => [c.slug, c.lang]), [['b', 'en'], ['a', 'en']]);
  assert.equal(cardsFor(list, 'ja')[0].href, 'narrator.html?sample=b&lang=ja');
  assert.deepEqual(cardsFor(null, 'ja'), []);
});
