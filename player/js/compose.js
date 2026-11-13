// 段4a の後半「この見本を元に、AI と台本を書く」: 見本の台本と絵の説明から、チャット AI へのプロンプトを作る。純粋な関数だけ（node --test で守る）。
// 返ってきた台本は「台本を貼る」と同じ道で開く（骨組みが見本と同じなら、見本の絵と音で開く）。
// チャット AI へ渡るのは、見本の台本と絵の説明だけ。家族の名前や写真は要らない（プロンプトの頭に書く）。

/** 見本の plan.md（絵のプロンプト）から、枚ごとの絵の説明 [{ slide, scene }]。
 *  `### [Prompt N]` のコードブロックの最初の段落だけ（画風の [Prompt style] と、文字の注意などのあとの段落は入れない） */
export function pictureScenes(planMd) {
  const lines = String(planMd || '').replace(/\r\n?/g, '\n').split('\n');
  const out = [];
  for (let i = 0; i < lines.length; i++) {
    const m = /^### \[Prompt ([0-9]+)\]/.exec(lines[i]);
    if (!m) continue;
    let j = i + 1;
    while (j < lines.length && !/^```/.test(lines[j]) && !/^#{1,3} /.test(lines[j])) j++;
    if (j >= lines.length || !/^```/.test(lines[j])) continue;
    const para = [];
    for (j++; j < lines.length && !/^```/.test(lines[j]); j++) {
      if (!lines[j].trim()) { if (para.length) break; continue; }
      para.push(lines[j].trim());
    }
    if (para.length) out.push({ slide: Number(m[1]), scene: para.join('\n') });
  }
  return out;
}

const WORDS = {
  ja: {
    intro: (title, n) => `紙芝居の見本「${title}」（${n}枚）を元に、語る人の話の台本（script.md）を書くのを手伝ってください。絵・絵の上の文字・音楽と効果音は、見本のものをそのまま使います。`,
    names: '家族の名前や写真は、あなたに渡さなくてかまいません（必要なら、呼び名や「娘」「友だち」のように書きます）。',
    first: '# はじめに',
    ask: 'まだ台本を書かないでください。先に語る人へ、問いを2〜3個、1つずつ聞いてください（だれに向けて語るか・どんな話にしたいか・その人自身の思い出や気持ち）。答えを聞いてから書きます',
    rules: '# 約束',
    rule: (n) => [
      'あなたが話を作らないでください。語る人自身の話・思い出は、聞いた言葉のまま、短い行に整えます',
      '家族の呼び方（親や子の続柄・名前・呼び名）は、語る人が使ったものだけを使います',
      `枚の数（${n}枚）と順は、見本のままにします。「---」の区切りも残します`,
      '「> [Picture]」「> [Text]」「> [BGM]」（[BGM once]・[BGM stop] なども）「> [Sound]」「> [Video]」の行と、そのすぐ下に続く「>」の行（絵の上の文字）は、一字も変えません',
      '語る人への演出の指示（ほかの「>」の行）は、新しい話に合わせて書き直してかまいません',
      '作品の題（「# 」の行）と、枚の題（「## [Slide N]」のあと）は、変えてかまいません',
      '絵は見本のままです。下の「絵の説明」と食い違わない話にします',
      '見本と同じ書き方にそろえます（「／」は短い区切り、「♩」はひと呼吸）',
      '健康や病気への効き目は、語る人が確かめたことでなければ言い切らず、「〜と聞いた」の形にします',
      '語る人自身の言葉の行（思い出・気持ち）は、行の頭に半角の「~ 」を付けます。あとで語る人が自分の言葉に直せる所になります',
      '「[Slide N]」「[Picture]」などの角括弧の中の英語と、「> Language: ja」の行は、訳さず残します',
      '書き上がったら、台本の全体を1つのコードブロックにまとめてください。説明はコードブロックの外に短く',
    ],
    scenes: '# 絵の説明（見本の絵に描いてあるもの）',
    slide: (n) => `${n}枚目`,
    script: '# 見本の台本',
  },
  en: {
    intro: (title, n) => `Please help me write a script (script.md) for the narrator's own story, based on the sample picture-story show "${title}" (${n} slides). The pictures, the words on them, and the music and sounds stay the sample's.`,
    names: 'You do not need the family\'s names or photos (if needed, write a nickname, or "my daughter", "a friend").',
    first: '# First',
    ask: 'Do not write the script yet. First ask the narrator two or three questions, one at a time (whom they will tell it to, what kind of story they want, their own memories and feelings). Write only when you have the answers',
    rules: '# Rules',
    rule: (n) => [
      'Do not make up the story. The narrator\'s own story and memories are shaped from their own words into short lines',
      'Call family members only by the words the narrator used (relations, names, nicknames)',
      `Keep the number of slides (${n}) and their order as in the sample. Keep the "---" between them`,
      'Do not change a single letter of the "> [Picture]", "> [Text]", "> [BGM]" (also [BGM once], [BGM stop] ...), "> [Sound]" and "> [Video]" lines, or the ">" lines right below them (the words on the picture)',
      'The narrator\'s stage directions (the other ">" lines) may be rewritten to fit the new story',
      'The title of the work (the "# " line) and the slide titles (after "## [Slide N]") may change',
      'The pictures stay the sample\'s. Tell a story that does not contradict the "Pictures" below',
      'Write the same way as the sample ("/" is a short pause, "♩" is a breath)',
      'Do not state that something helps health or illness unless the narrator has checked it; write "I heard that ..." instead',
      'Start the lines in the narrator\'s own words (memories, feelings) with "~ " (a plain tilde and a space). The narrator can change those lines later',
      'Keep "[Slide N]", "[Picture]" and the other words in square brackets, and the "> Language: en" line, as they are',
      'When it is written, put the whole script in one code block. Keep any explanation short and outside the code block',
    ],
    scenes: '# Pictures (what the sample\'s pictures show)',
    slide: (n) => `Slide ${n}`,
    script: '# The sample\'s script',
  },
};

/** 見本を元に台本を書くプロンプト。script: 見本の script.md、scenes: pictureScenes の結果、slides: 枚の数 */
export function buildComposePrompt({ lang, title, slides, script, scenes }) {
  const w = String(lang).toLowerCase().startsWith('ja') ? WORDS.ja : WORDS.en;
  const out = [w.intro(title, slides), w.names, '', w.first, w.ask, '', w.rules, ...w.rule(slides).map((r) => `- ${r}`)];
  const shown = (scenes || []).filter((s) => s.slide >= 1 && s.slide <= slides);
  if (shown.length) {
    out.push('', w.scenes);
    for (const s of shown) out.push('', `## ${w.slide(s.slide)}`, s.scene);
  }
  const body = String(script).replace(/\r\n?/g, '\n').replace(/\n+$/, '');
  const fence = '`'.repeat(Math.max(3, ...[...body.matchAll(/`{3,}/g)].map((m) => m[0].length + 1)));
  out.push('', w.script, '', fence + 'markdown', body, fence);
  return out.join('\n') + '\n';
}
