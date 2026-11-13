// 段3「AI に相談」（player/js/advise.js）
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { holeSection, isOwnStory, slideBlocks, buildPrompt, parseAnswer } from '../../player/js/advise.js';
import { holeRuns } from '../../player/js/variant.js';

const GUIDE = [
  '# Guide', '', '| Hole | Where |', '|---|---|', '| 1 | Slide 1 |', '', '---', '',
  '## Hole 1: Why we keep the lamp (slide 1)', '', '**Where**: slide 1.', '',
  '**Questions to help you find your story**:', '- Who lit it first?', '', '---', '',
  '## Hole 12: Something else', '', 'text', '',
  '## Hole 2: The storm (slide 2)', '', '**Where**: slide 2.', '',
].join('\n');

test('holeSection: 穴 n の節だけ（穴1 と 穴12 を取り違えない）', () => {
  const s = holeSection(GUIDE, 1);
  assert.ok(s.startsWith('## Hole 1: Why we keep the lamp'));
  assert.ok(!s.includes('Hole 12') && !s.includes('---'));
  assert.ok(holeSection(GUIDE, 2).startsWith('## Hole 2: The storm'));
  assert.equal(holeSection(GUIDE, 9), '');
  assert.ok(holeSection('## 穴3 序幕\n\n本文\n\n---\n', 3).startsWith('## 穴3 序幕'));
});

test('isOwnStory: 手引きに「問い」がある穴', () => {
  assert.ok(isOwnStory(holeSection(GUIDE, 1)));
  assert.ok(!isOwnStory(holeSection(GUIDE, 2)));
  assert.ok(isOwnStory('**自分の話を見つける問い**:\n- 何だろう'));
});

test('slideBlocks: 替える所と変えない所。演出の行は入れない・印は外す', () => {
  const notes = '> a cue\n\nKeep this.\n\n~1 Change this\n~1 and this.\n\n~2 Another hole.\n\n~1 Change again.';
  assert.deepEqual(slideBlocks(notes, 1), [
    { kind: 'keep', text: 'Keep this.' },
    { kind: 'change', text: 'Change this\nand this.' },
    { kind: 'keep', text: 'Another hole.' },
    { kind: 'change', text: 'Change again.' },
  ]);
});

const SLIDES = [
  { number: 1, title: 'Cover', notes: 'Keep this.\n\n~1 Our lamp\n~1 is old.' },
  { number: 2, title: 'Storm', notes: 'No hole here.' },
  { number: 3, title: 'End', notes: '~1 First part.\n\nKeep.\n\n~1 Second part.' },
];

test('buildPrompt: 約束・手引き・この穴がかかる枚だけ。語る人自身の話なら問いを先に', () => {
  const p = buildPrompt({ lang: 'en', title: 'The Lamp', hole: 1, section: holeSection(GUIDE, 1), slides: SLIDES });
  assert.ok(p.includes('You do not need the family\'s names or photos'));
  assert.ok(p.includes('Do not make one up'));
  assert.ok(p.includes('## [Slide 1] Cover') && p.includes('## [Slide 3] End') && !p.includes('[Slide 2] Storm'));
  assert.ok(p.includes('### To change\nOur lamp\nis old.'));
  assert.ok(!p.includes('~1'));
  const q = buildPrompt({ lang: 'ja', title: '灯台', hole: 2, section: holeSection(GUIDE, 2), slides: SLIDES });
  assert.ok(q.includes('家族の名前や写真は') && !q.includes('話を作らないで'));
  assert.ok(q.includes('「／」は短い区切り') && q.includes('「〜と聞いた」の形'));
  assert.ok(p.includes('"/" is a short pause') && p.includes('I heard that'));
});

test('parseAnswer: 枚ごとに分け、その枚の欄へ順に（コードブロックの中だけ・印は外す）', () => {
  const runs = holeRuns('# T\n\n## [Slide 1] Cover\n\nKeep.\n\n~1 a\n~1 b\n\n## [Slide 3] End\n\n~1 c\n\nKeep.\n\n~1 d\n')
    .map((r) => ({ ...r }));
  const answer = 'Here you are:\n```\n[Slide 1]\nOur lamp\nis new.\n\n[Slide 3] End\n~1 First, new.\n\nSecond, new.\n```\nHope it helps.';
  assert.deepEqual(parseAnswer(answer, runs), { texts: { 0: 'Our lamp\nis new.', 1: 'First, new.', 2: 'Second, new.' } });
});

test('parseAnswer: 数が合わない・知らない枚・見出しが無いときは止まる', () => {
  const runs = holeRuns('# T\n\n## [Slide 3] End\n\n~1 c\n\nKeep.\n\n~1 d\n');
  assert.deepEqual(parseAnswer('[Slide 3]\nonly one', runs), { error: 'count', slide: 3, want: 2, got: 1 });
  assert.deepEqual(parseAnswer('[Slide 9]\nx', runs), { error: 'slide', slide: 9 });
  assert.deepEqual(parseAnswer('just words', runs), { error: 'no-slides' });
});

// 公開の見本で通す（台本の文はテストに写さない）
for (const lang of ['ja', 'en']) {
  test(`見本（six-friends-smoothie/${lang}）: 穴1のプロンプトは問いを先に聞かせ、答えを戻せる`, () => {
    const dir = new URL(`../../examples/six-friends-smoothie/${lang}/`, import.meta.url);
    const script = readFileSync(new URL('script.md', dir), 'utf8');
    const work = JSON.parse(readFileSync(new URL('work.json', dir), 'utf8'));
    const section = holeSection(readFileSync(new URL('holes.md', dir), 'utf8'), 1);
    assert.ok(section && isOwnStory(section), '穴1は語る人自身の話（手引きに問いがある）');
    const p = buildPrompt({ lang, title: work.title, hole: 1, section, slides: work.slides });
    for (const n of [1, 4, 5]) assert.ok(p.includes(`## [Slide ${n}]`), `slide ${n}`);
    const runs = holeRuns(script).filter((r) => r.hole === '1');
    const bySlide = Map.groupBy(runs, (r) => r.slide);
    const answer = '```\n' + [...bySlide].map(([n, rs]) => `[Slide ${n}]\n` + rs.map((r) => `new ${r.index}`).join('\n\n')).join('\n\n') + '\n```';
    const got = parseAnswer(answer, runs);
    assert.deepEqual(got, { texts: Object.fromEntries(runs.map((r) => [r.index, `new ${r.index}`])) });
  });
}
