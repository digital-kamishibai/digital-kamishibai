// 配った見本の語りを少し変えた版（player/js/variant.js）
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  holeRuns, applyTexts, changedRuns, sameOutsideHoles, changedSummary, withHeader, basedOn, makeVariant, variantWork, CREDIT,
  skeletonDiffs, pickBySkeleton, narrationSummary, makeMade, wideMarks, fixWideMarks, unfence,
} from '../../player/js/variant.js';
import { readScript } from '../../player/js/script.js';

const SCRIPT = [
  '# The Lamp',
  '',
  '> Language: en',
  '',
  '## [Slide 1] Cover',
  '',
  '> [Picture] pictures/01.jpg',
  '',
  '~1 Tonight I will tell you',
  '~1 about our lamp.',
  '',
  'A plain line, then',
  '~2 a marked line in the same paragraph.',
  '',
  '## [Slide 2] Storm',
  '',
  '~1 It went out once.',
  '',
  'The end.',
  '',
  '---',
  '',
  '~1 after the end mark: not read',
  '',
].join('\n');
const META = { title: 'The Lamp', slug: 'the-lamp', lang: 'en', version: 3 };

test('holeRuns: 同じ印の行の連なりを1つの欄に（印の無い行・空行・"---" の後で切れる）', () => {
  const runs = holeRuns(SCRIPT);
  assert.deepEqual(runs.map((r) => [r.slide, r.hole, r.text]), [
    [1, '1', 'Tonight I will tell you\nabout our lamp.'],
    [1, '2', 'a marked line in the same paragraph.'],
    [2, '1', 'It went out once.'],
  ]);
  assert.deepEqual(holeRuns('# T\n\n## [Slide 1] A\n\n~1 a\n~2 b\n~ c\n'), holeRuns('# T\n\n## [Slide 1] A\n\n~1 a\n~2 b\n~ c\n'));
  assert.equal(holeRuns('# T\n\n## [Slide 1] A\n\n~1 a\n~2 b\n~ c\n').length, 3);
});

test('applyTexts: 欄の文に印を付け直して差し替える。ほかの行は一字も変えない', () => {
  const out = applyTexts(SCRIPT, { 0: 'Tonight, a story\n\nabout a lamp we keep  ' });
  assert.ok(out.includes('~1 Tonight, a story\n~1 about a lamp we keep\n'), out);
  assert.ok(sameOutsideHoles(SCRIPT, out), '欄の中の空行は落とす（段落を分けない）');
  assert.deepEqual(changedRuns(SCRIPT, out), [0]);
  const one = applyTexts(SCRIPT, { 2: 'It went dark.' });
  assert.deepEqual(changedRuns(SCRIPT, one), [2]);
});

test('applyTexts: 空の欄は印だけの行を1つ残す（その穴は語らない。欄の数は変わらない）', () => {
  const out = applyTexts(SCRIPT, { 1: '   ' });
  assert.ok(out.includes('A plain line, then\n~2 \n'), out);
  assert.deepEqual(changedRuns(SCRIPT, out), [1]);
});

test('applyTexts: 欄に書いた見出しや合図は、印が付いて語りのまま（台本の形を崩せない）', () => {
  const out = applyTexts(SCRIPT, { 2: 'x\n## [Slide 9] Injected\n> [Video] https://youtu.be/8KkKuTCFvzI' });
  const r = readScript(out);
  assert.equal(r.work.slides.length, 2);
  assert.ok(r.work.slides[1].notes.includes('~1 ## [Slide 9] Injected'));
  assert.deepEqual(r.work.slides[1].cues, []);
});

test('withHeader・basedOn: 見出しに Based on・Changed（前にあれば置き換える）', () => {
  const v = withHeader(SCRIPT, META, 'hole 1 (slide 2)');
  const lines = v.split('\n');
  assert.equal(lines[3], `> Based on: The Lamp (the-lamp/en, version 3) — ${CREDIT}`);
  assert.equal(lines[4], '> Changed: hole 1 (slide 2)');
  const again = withHeader(v, { ...META, version: 4 }, 'hole 2 (slide 1)');
  assert.equal(again.split('\n').filter((l) => l.includes('Based on:')).length, 1);
  assert.deepEqual(basedOn(again), { slug: 'the-lamp', lang: 'en', version: 4 });
  assert.equal(basedOn(SCRIPT), null);
  // 題に括弧があっても、最後の (slug/lang, version N) を読む
  assert.deepEqual(basedOn(withHeader(SCRIPT, { ...META, title: 'A (b/c, version 9) story' }, '')), { slug: 'the-lamp', lang: 'en', version: 3 });
  assert.ok(sameOutsideHoles(SCRIPT, again));
});

test('changedSummary: 穴ごとに乗っている枚（ja・en）', () => {
  const runs = holeRuns(SCRIPT);
  assert.equal(changedSummary(runs, [0, 2, 1], 'en'), 'hole 1 (slides 1, 2); hole 2 (slide 1)');
  assert.equal(changedSummary(runs, [0, 2], 'ja'), '穴1（1・2枚目）');
});

test('makeVariant → readScript → variantWork: 見本の work.json の語りだけが替わる', () => {
  const variant = makeVariant(SCRIPT, { 0: 'Tonight, our own lamp story.' }, META);
  const sampleRead = readScript(SCRIPT);
  const sampleWork = JSON.parse(JSON.stringify(sampleRead.work));
  sampleWork.slides[0].picture = 'pictures/_built/01.jpg';      // 見本は焼いた絵を指す——そのまま使う
  const r = variantWork(sampleWork, sampleRead, readScript(variant));
  assert.ok(r.work, JSON.stringify(r));
  assert.equal(r.work.slides[0].picture, 'pictures/_built/01.jpg');
  assert.ok(r.work.slides[0].notes.startsWith('~1 Tonight, our own lamp story.'));
  assert.equal(r.work.slides[1].notes, sampleWork.slides[1].notes);
  assert.ok(variant.includes('> Changed: hole 1 (slide 1)'));
});

test('variantWork: 合図や枚が見本と違えば開かない', () => {
  const sampleRead = readScript(SCRIPT);
  const extra = SCRIPT.replace('## [Slide 2] Storm\n', '## [Slide 2] Storm\n\n> [Sound] sounds/x.mp3\n');
  assert.deepEqual(variantWork(sampleRead.work, sampleRead, readScript(extra)), { error: 'slide', slide: 2, diffs: [{ what: 'cues', slide: 2 }] });
  assert.equal(sameOutsideHoles(SCRIPT, extra), false);
  assert.equal(variantWork(sampleRead.work, sampleRead, readScript('# T\n')).error, 'read');
});

// 公開の見本で通す（台本の文はテストに写さない）
for (const lang of ['ja', 'en']) {
  test(`見本（six-friends-smoothie/${lang}）: 黄色い所をすべて替えても、見本の work.json の語りだけが替わる`, () => {
    const dir = new URL(`../../examples/six-friends-smoothie/${lang}/`, import.meta.url);
    const script = readFileSync(new URL('script.md', dir), 'utf8');
    const work = JSON.parse(readFileSync(new URL('work.json', dir), 'utf8'));
    const runs = holeRuns(script);
    assert.ok(runs.length >= 3 && runs.every((r) => r.hole === '1'));
    const texts = Object.fromEntries(runs.map((r) => [r.index, `changed ${r.index}`]));
    const variant = makeVariant(script, texts, { title: work.title, slug: 'six-friends-smoothie', lang, version: 2 });
    assert.ok(sameOutsideHoles(script, variant));
    assert.deepEqual(changedRuns(script, variant), runs.map((r) => r.index));
    const r = variantWork(work, readScript(script), readScript(variant));
    assert.ok(r.work, JSON.stringify(r));
    r.work.slides.forEach((s, i) => {
      assert.equal(s.picture, work.slides[i].picture);
      assert.deepEqual(s.cues, work.slides[i].cues);
    });
    assert.deepEqual(basedOn(variant), { slug: 'six-friends-smoothie', lang, version: 2 });
  });
}

// ---------- 見本を元に書いた台本（段4a。docs/work-format.md §6「A script written from a sample」） ----------

// 黄色でない語り・枚の題・作品の題を替えた台本（骨組みは SCRIPT のまま）
const MADE = SCRIPT
  .replace('# The Lamp', '# The Kite')
  .replace('## [Slide 1] Cover', '## [Slide 1] Opening')
  .replace('A plain line, then', 'A plain line about a kite,')
  .replace('The end.', 'It flew away.');

test('skeletonDiffs: 語り・題が違っても骨組みが同じなら []、違う所は枚ごとに全部', () => {
  const sampleRead = readScript(SCRIPT);
  assert.deepEqual(skeletonDiffs(sampleRead, readScript(MADE)), []);
  const bad = MADE
    .replace('> [Picture] pictures/01.jpg', '> [Picture] pictures/09.jpg')
    .replace('## [Slide 2] Storm\n', '## [Slide 2] Storm\n\n> [Sound] sounds/x.mp3\n');
  assert.deepEqual(skeletonDiffs(sampleRead, readScript(bad)), [{ what: 'picture', slide: 1 }, { what: 'cues', slide: 2 }]);
  const more = `${MADE}\n## [Slide 3] More\n\nOne more.\n`;
  assert.deepEqual(skeletonDiffs(sampleRead, readScript(more)), [{ what: 'slides', sample: 2, script: 3 }]);
});

test('skeletonDiffs: [Text] が違う枚も止める（焼いた絵が合わない）', () => {
  const withText = SCRIPT.replace('> [Picture] pictures/01.jpg', '> [Picture] pictures/01.jpg\n\n> [Text] place top\n> The Lamp');
  const sampleRead = readScript(withText);
  assert.ok(sampleRead.work, JSON.stringify(sampleRead.errors));
  assert.deepEqual(skeletonDiffs(sampleRead, readScript(withText.replace('> The Lamp', '> The Kite'))), [{ what: 'text', slide: 1 }]);
  assert.deepEqual(skeletonDiffs(sampleRead, readScript(withText.replace('The end.', 'It flew away.'))), []);
});

test('variantWork: 段4a の台本は、作品の題・枚の題・語りだけが替わる（絵・合図は見本のまま）', () => {
  const sampleRead = readScript(SCRIPT);
  const sampleWork = sampleRead.work;
  const r = variantWork(sampleWork, sampleRead, readScript(MADE));
  assert.ok(r.work, JSON.stringify(r));
  assert.equal(r.work.title, 'The Kite');
  assert.equal(r.work.slides[0].title, 'Opening');
  assert.ok(r.work.slides[1].notes.includes('It flew away.'));
  r.work.slides.forEach((s, i) => {
    assert.equal(s.picture, sampleWork.slides[i].picture);
    assert.deepEqual(s.cues, sampleWork.slides[i].cues);
  });
  assert.equal(sameOutsideHoles(SCRIPT, MADE), false, '段2の道には入らない');
});

test('pickBySkeleton: 骨組みが同じ見本が1つなら選ぶ。0なら none（いちばん近い見本も）、2つ以上なら many', () => {
  const read = readScript(MADE);
  const lamp = { entry: { slug: 'the-lamp' }, read: readScript(SCRIPT) };
  const other = { entry: { slug: 'other' }, read: readScript(SCRIPT.replace('pictures/01.jpg', 'pictures/02.jpg')) };
  assert.deepEqual(pickBySkeleton([other, lamp], read), { entry: { slug: 'the-lamp' } });
  assert.deepEqual(pickBySkeleton([other], read), { none: true, nearest: { entry: { slug: 'other' }, diffs: [{ what: 'picture', slide: 1 }] } });
  const far = { entry: { slug: 'far' }, read: readScript(SCRIPT.replace('pictures/01.jpg', 'pictures/03.jpg').replace('## [Slide 2] Storm\n', '## [Slide 2] Storm\n\n> [Sound] s.mp3\n')) };
  assert.equal(pickBySkeleton([far, other], read).nearest.entry.slug, 'other', '違う所のいちばん少ない見本');
  assert.equal(pickBySkeleton([other, { ...other, entry: { slug: 'tie' } }], read).nearest, null, '同じくらい近い見本が2つなら言わない');
  assert.equal(pickBySkeleton([lamp], readScript('# T\n\n## [Slide 1] A\n\nhi\n')).nearest, null, '枚の数が違えば近いとは言わない');
  assert.deepEqual(pickBySkeleton([lamp, { ...lamp, entry: { slug: 'copy' } }], read), { many: [{ slug: 'the-lamp' }, { slug: 'copy' }] });
});

test('narrationSummary・makeMade: Changed に語りの変わった枚。Based on は無ければ足す。ほかの行は変えない', () => {
  const sampleRead = readScript(SCRIPT);
  assert.equal(narrationSummary(sampleRead, readScript(MADE), 'en'), 'narration (slides 1–2)');
  assert.equal(narrationSummary(sampleRead, readScript(MADE), 'ja'), '語り（1〜2枚目）');
  assert.equal(narrationSummary(sampleRead, readScript(SCRIPT.replace('The end.', 'Fin.')), 'en'), 'narration (slide 2)');
  const out = makeMade(MADE, {}, META, sampleRead, readScript);
  assert.deepEqual(basedOn(out), { slug: 'the-lamp', lang: 'en', version: 3 });
  assert.ok(out.includes('> Changed: narration (slides 1–2)'), out);
  assert.equal(out.split('\n').filter((l) => !/^> (Based on|Changed):/.test(l)).join('\n'), MADE);
  // 貼った台本の黄色い所を欄で替える
  const edited = makeMade(MADE, { 0: 'A new opening.' }, META, sampleRead, readScript);
  assert.ok(edited.includes('~1 A new opening.\n'));
  assert.ok(edited.includes('A plain line about a kite,'));
  // 2回書いても Based on・Changed は1つずつ
  const again = makeMade(out, {}, META, sampleRead, readScript);
  assert.equal(again.split('\n').filter((l) => /^> Based on:/.test(l)).length, 1);
});

test('wideMarks・fixWideMarks: 行頭の全角の印を数え、半角に直す（全角の数字も）。ほかの「～」は触らない', () => {
  const text = '# T\n\n## [Slide 1] A\n\n～ one\n〜１ two\n～2　three\nwave ～ here\n～no space\n';
  assert.equal(wideMarks(text), 3);
  const fixed = fixWideMarks(text);
  assert.equal(fixed, '# T\n\n## [Slide 1] A\n\n~ one\n~1 two\n~2 three\nwave ～ here\n～no space\n');
  assert.equal(wideMarks(fixed), 0);
  assert.deepEqual(holeRuns(fixed).map((r) => r.hole), ['', '1', '2']);
});

// 公開の見本で通す: 黄色でない語りを全部替えても、骨組みが同じなら見本の絵と素材のまま開ける（台本の文はテストに写さない）
for (const lang of ['ja', 'en']) {
  test(`見本（six-friends-smoothie/${lang}）: 語りをすべて替えた台本は段4a の道で開ける`, () => {
    const dir = new URL(`../../examples/six-friends-smoothie/${lang}/`, import.meta.url);
    const script = readFileSync(new URL('script.md', dir), 'utf8');
    const work = JSON.parse(readFileSync(new URL('work.json', dir), 'utf8'));
    const sampleRead = readScript(script);
    // 語りの行（合図・制作メモ・見出し・印の付いた行のほか）を、すべて別の文に
    let n = 0;
    const made = script.replace(/\r\n?/g, '\n').split('\n').map((l) => (
      /^[^\s#>~\-\[<*|]/.test(l) && !/^\*\*/.test(l) ? `line ${++n}` : l)).join('\n');
    assert.ok(n > 10);
    assert.equal(sameOutsideHoles(script, made), false);
    const read = readScript(made);
    assert.ok(read.work, JSON.stringify(read.errors));
    assert.deepEqual(skeletonDiffs(sampleRead, read), []);
    assert.deepEqual(pickBySkeleton([{ entry: { slug: 'six-friends-smoothie' }, read: sampleRead }], read), { entry: { slug: 'six-friends-smoothie' } });
    const r = variantWork(work, sampleRead, read);
    assert.ok(r.work, JSON.stringify(r));
    r.work.slides.forEach((s, i) => {
      assert.equal(s.picture, work.slides[i].picture);
      assert.deepEqual(s.cues, work.slides[i].cues);
    });
    assert.notDeepEqual(r.work.slides.map((s) => s.notes), work.slides.map((s) => s.notes));
  });
}

test('段4a の台本で開いた作品でも、聞き手への welcome に語りは入らない（題は台本のもの）', async () => {
  const { welcomeMessage } = await import('../../player/js/protocol.js');
  const sampleRead = readScript(SCRIPT);
  const r = variantWork(sampleRead.work, sampleRead, readScript(MADE));
  const w = welcomeMessage(r.work, new Map([[1, { mime: 'image/jpeg', size: 1 }]]));
  const sent = JSON.stringify(w);
  assert.equal(w.title, 'The Kite');
  for (const s of r.work.slides) for (const line of s.notes.split('\n').filter(Boolean)) assert.ok(!sent.includes(line), line);
});

test('unfence: 台本の全体が1つのコードブロックなら中身だけ（チャット AI の答えを枠ごと貼ったとき）', () => {
  assert.equal(unfence('```\n# T\n\nhi\n```'), '# T\n\nhi');
  assert.equal(unfence('\n```markdown\n# T\n```\n\n'), '# T');
  assert.equal(unfence('~~~~\n# T\n~~~~'), '# T');
  assert.equal(unfence('# T\n\nhi\n'), '# T\n\nhi\n', 'コードブロックでなければそのまま');
  assert.equal(unfence('```\n# T\n~~~'), '```\n# T\n~~~', '閉じの記号が違えばそのまま');
  assert.equal(unfence('Here it is:\n```\n# T\n```'), 'Here it is:\n```\n# T\n```', '枠の外に文があればそのまま');
});
