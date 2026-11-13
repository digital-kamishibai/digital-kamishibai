// 段3「AI に相談」: 穴1つ分のプロンプトを作り、チャット AI の答えを欄へ戻す。純粋な関数だけ（node --test で守る）。
// 語る人自身の話の穴（手引きに「自分の話を見つける問い」がある穴）は、AI に話を作らせず、先に問いを聞かせる。
// チャット AI へ渡るのは、見本の台本のその枚の語りと手引きだけ。家族の名前や写真は要らない（プロンプトの頭に書く）。

import { holeLine } from './work.js';

const QUESTIONS = /\*\*(自分の話を見つける問い|Questions to help you find your story)\*\*/;

/** 手引き（holes.md）の穴 n の節（見出しの行から、次の "---" か次の見出しの前まで）。無ければ '' */
export function holeSection(holesMd, n) {
  const lines = String(holesMd || '').replace(/\r\n?/g, '\n').split('\n');
  const head = new RegExp(`^## (?:穴${n}(?![0-9])|Hole ${n}(?![0-9]))`);
  const start = lines.findIndex((l) => head.test(l));
  if (start < 0) return '';
  let end = lines.length;
  for (let i = start + 1; i < lines.length; i++) if (lines[i] === '---' || /^## /.test(lines[i])) { end = i; break; }
  return lines.slice(start, end).join('\n').trim();
}

/** 語る人自身の話の穴か（AI に話を作らせない） */
export const isOwnStory = (section) => QUESTIONS.test(section);

/** その枚の語り（notes）を、穴 n の「替える所」と「変えない所」の連なりに分ける。演出の行（> ）は入れない */
export function slideBlocks(notes, n) {
  const blocks = [];
  for (const line of String(notes).split('\n')) {
    if (line.startsWith('>')) continue;
    const h = holeLine(line);
    const kind = h && h.hole === String(n) ? 'change' : 'keep';
    const text = h ? h.text : line;
    const last = blocks[blocks.length - 1];
    if (last && last.kind === kind) last.lines.push(text);
    else if (text.trim() || last) blocks.push({ kind, lines: [text] });
  }
  return blocks
    .map((b) => ({ kind: b.kind, text: b.lines.join('\n').replace(/^\n+|\n+$/g, '') }))
    .filter((b) => b.text.trim());
}

const WORDS = {
  ja: {
    intro: (title, n) => `紙芝居「${title}」の台本の一部（穴${n}）を、語る人の言葉に替えるのを手伝ってください。`,
    names: '家族の名前や写真は、あなたに渡さなくてかまいません（必要なら、呼び名や「娘」「友だち」のように書きます）。',
    rules: '# 約束',
    rule: [
      '「替える所」だけを書き直してください。「変えない所」は流れを読むためのもので、変えません',
      '答えは語る文だけにします。説明や演出の指示は書きません',
      '改行を大事にします。1行は短く、息継ぎの所で切ります',
      '変えない所と同じ書き方にそろえます（「／」は短い区切り、「♩」はひと呼吸）',
      '健康や病気への効き目は、語る人が確かめたことでなければ言い切らず、「〜と聞いた」の形にします',
      '答えは、枚ごとに「[Slide N]」の見出しを付けて、全部を1つのコードブロックにまとめてください。1つの枚に替える所がいくつかあるときは、空行で分け、同じ数・同じ順にします',
      '行の頭に「~」や「>」は付けません',
    ],
    own: 'この穴は、語る人自身の話です。あなたが話を作らないでください。まず、下の手引きの「問い」から2〜3個を、1つずつ聞いてください。答えを聞いてから、その人の言葉のまま、短い行に整えてください',
    guide: '# 穴の手引き',
    script: '# 台本（この穴がかかる枚）',
    change: '### 替える所',
    keep: '### 変えない所',
    shape: '答えの形:',
    first: '（1つ目の替える所）',
    second: '（2つ目の替える所。あるときだけ）',
  },
  en: {
    intro: (title, n) => `Please help me put part of the script of the picture-story show "${title}" (hole ${n}) in the narrator's own words.`,
    names: 'You do not need the family\'s names or photos (if needed, write a nickname, or "my daughter", "a friend").',
    rules: '# Rules',
    rule: [
      'Rewrite only the parts marked "To change". The parts marked "Keep" are there so you can follow the story; do not change them',
      'Answer with the words to be read aloud only. No explanations or stage directions',
      'Line breaks matter. Keep lines short, breaking where the narrator takes a breath',
      'Write the same way as the parts marked "Keep" ("/" is a short pause, "♩" is a breath)',
      'Do not state that something helps health or illness unless the narrator has checked it; write "I heard that ..." instead',
      'Give each slide a heading "[Slide N]", and put the whole answer in one code block. When a slide has more than one part to change, separate them with a blank line, the same number of parts in the same order',
      'Do not start lines with "~" or ">"',
    ],
    own: 'This hole is the narrator\'s own story. Do not make one up. First ask two or three of the "questions" in the guide below, one at a time. When you have the answers, shape the person\'s own words into short lines',
    guide: '# The guide to this hole',
    script: '# The script (the slides this hole is on)',
    change: '### To change',
    keep: '### Keep',
    shape: 'The shape of the answer:',
    first: '(the first part to change)',
    second: '(the second part to change, only if there is one)',
  },
};

/** 穴1つ分のプロンプト。slides: [{ number, title, notes }]（いまの語り。変えた欄があれば、それを入れた語り） */
export function buildPrompt({ lang, title, hole, section, slides }) {
  const w = String(lang).toLowerCase().startsWith('ja') ? WORDS.ja : WORDS.en;
  const out = [w.intro(title, hole), w.names, '', w.rules, ...w.rule.map((r) => `- ${r}`)];
  if (isOwnStory(section)) out.push(`- ${w.own}`);
  out.push('', w.shape, '```', '[Slide N]', w.first, '', w.second, '```', '', w.guide, '', section, '', w.script);
  for (const s of slides) {
    const blocks = slideBlocks(s.notes, hole);
    if (!blocks.some((b) => b.kind === 'change')) continue;
    out.push('', `## [Slide ${s.number}] ${s.title}`.trimEnd());
    for (const b of blocks) out.push('', b.kind === 'change' ? w.change : w.keep, b.text);
  }
  return out.join('\n') + '\n';
}

/** チャット AI の答え → 欄の文 { texts: { 欄の番号: 文 } }、または { error, slide?, want?, got? }。
 *  runs: その穴の欄（variant.js の holeRuns から、その穴のものだけ）。コードブロックがあれば、その中だけを読む */
export function parseAnswer(answer, runs) {
  let text = String(answer || '').replace(/\r\n?/g, '\n');
  const fence = /```[^\n]*\n([\s\S]*?)```/.exec(text);
  if (fence) text = fence[1];
  const parts = text.split(/^[ \t]*\[Slide ([0-9]+)\][^\n]*$/m);
  if (parts.length < 3) return { error: 'no-slides' };
  const texts = {};
  for (let i = 1; i < parts.length; i += 2) {
    const slide = Number(parts[i]);
    const mine = runs.filter((r) => r.slide === slide);
    if (!mine.length) return { error: 'slide', slide };
    const paras = parts[i + 1].split(/\n[ \t]*\n/).map((p) => p.split('\n').map((l) => l.replace(/^[ \t]*[~>][0-9]*[ \t]?/, '').trimEnd())
      .filter((l) => l.trim()).join('\n')).filter(Boolean);
    if (mine.length === 1) texts[mine[0].index] = paras.join('\n');
    else if (paras.length === mine.length) mine.forEach((r, k) => { texts[r.index] = paras[k]; });
    else return { error: 'count', slide, want: mine.length, got: paras.length };
  }
  return { texts };
}
