// 段4a の後半「この見本を元に、AI と台本を書く」（player/js/compose.js）
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { pictureScenes, buildComposePrompt } from '../../player/js/compose.js';

const PLAN = [
  '# Picture prompts', '', 'Intro.', '',
  '### [Prompt style]', '', '```text', 'Soft watercolour.', '```', '',
  '### [Prompt 1] Cover', '', '```text', 'Scene: a lighthouse at dusk.', 'Waves below.', '',
  '[About text] Do not draw any letters.', '```', '',
  '### [Prompt 2] The storm', '', 'A note before the block.', '', '```text', '', 'A boat in high waves.', '```', '',
  '### [Prompt 3] No block here', '', 'Just words.', '',
  '### [Prompt 4] Last', '', '```', 'A calm harbour.', '```', '',
].join('\n');

test('pictureScenes: [Prompt N] のコードブロックの最初の段落だけ（画風・文字の注意は入れない）', () => {
  assert.deepEqual(pictureScenes(PLAN), [
    { slide: 1, scene: 'Scene: a lighthouse at dusk.\nWaves below.' },
    { slide: 2, scene: 'A boat in high waves.' },
    { slide: 4, scene: 'A calm harbour.' },
  ]);
  assert.deepEqual(pictureScenes(''), []);
  assert.deepEqual(pictureScenes(PLAN.replace(/\n/g, '\r\n'))[0].scene, 'Scene: a lighthouse at dusk.\nWaves below.');
});

const SCRIPT = [
  '# The Lamp', '', '> Language: en', '', '## [Slide 1] Cover', '', '> [Picture] pictures/01.jpg', '', 'Line one.', '',
  '---', '', '## [Slide 2] Storm', '', '> [Picture] pictures/02.jpg', '', '~1 My own line.', '',
].join('\n');

test('buildComposePrompt: 問いを先に・約束・絵の説明・見本の台本', () => {
  const p = buildComposePrompt({ lang: 'en', title: 'The Lamp', slides: 2, script: SCRIPT, scenes: pictureScenes(PLAN) });
  assert.ok(p.startsWith('Please help me write a script'));
  assert.ok(p.includes('(2 slides)'));
  assert.ok(p.includes('You do not need the family\'s names or photos'));
  assert.ok(p.includes('Do not write the script yet. First ask the narrator two or three questions, one at a time'));
  assert.ok(p.includes('Do not make up the story'));
  assert.ok(p.includes('Keep the number of slides (2)'));
  assert.ok(p.includes('may be rewritten to fit the new story'));
  assert.ok(p.includes('put the whole script in one code block'));
  // 絵の説明は枚の数の中だけ（4枚目の説明は2枚の見本には入れない）。画風・文字の注意は入らない
  assert.ok(p.includes('## Slide 1\nScene: a lighthouse at dusk.\nWaves below.'));
  assert.ok(p.includes('## Slide 2\nA boat in high waves.'));
  assert.ok(!p.includes('A calm harbour') && !p.includes('watercolour') && !p.includes('About text'));
  // 見本の台本は丸ごと、コードブロックに
  assert.ok(p.includes('```markdown\n' + SCRIPT.replace(/\n+$/, '') + '\n```\n'));
  assert.ok(p.indexOf('Pictures') < p.indexOf('The sample\'s script'));
});

test('buildComposePrompt: ja・絵の説明が無ければ節を出さない・台本にコードブロックがあれば囲いを長く', () => {
  const p = buildComposePrompt({ lang: 'ja-JP', title: '灯台', slides: 2, script: 'a\n```\nb\n', scenes: [] });
  assert.ok(p.startsWith('紙芝居の見本「灯台」（2枚）を元に'));
  assert.ok(p.includes('家族の呼び方（親や子の続柄・名前・呼び名）は、語る人が使ったものだけ'));
  assert.ok(p.includes('行の頭に半角の「~ 」を付けます'));
  assert.ok(!p.includes('絵の説明（'));
  assert.ok(p.includes('````markdown\na\n```\nb\n````\n'));
});
