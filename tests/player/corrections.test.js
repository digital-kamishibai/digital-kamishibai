import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  editable, sheetEnabled, mayReload, keepSlide, editorStep, paragraphs, boxFromFields, fieldsFromBox,
  diffNotes, diffOverlays, emptySheet, setSlideEdits, removeItem, judge, reconcile, applySheet,
  fence, sheetMarkdown, sheetName, readSheet, storageKey, isEmpty, pointSeat, clock, seatLines,
  markCut, cutLines, mediaLines, place, videoOf, askPicture, choosePicture, pictureLines, sheetCounts, workSig, commentStatus, removeComment, isOldComment, sheetGroups,
  setLinkVolume, linkVolumeNow, volumeLines, dbText,
} from '../../player/js/corrections.js';

const slide = (n, notes, overlays) => ({ number: n, title: '', picture: `pictures/0${n}.jpg`, notes, overlays, cues: [] });
const work = (slides, extra = {}) => ({ format: 'digital-kamishibai/work', version: 1, title: '小さな薪', language: 'ja', draft: true, slides, ...extra });

// ---------- 出してよいか（E1・E5・E10・決定5） ----------

test('直す欄は練習用の版で、受付を開いていないときだけ', () => {
  assert.equal(editable({ draft: true, roomOpen: false }), true);
  assert.equal(editable({ draft: true, roomOpen: true }), false);   // 本番（受付中）は直さない
  assert.equal(editable({ draft: false, roomOpen: false }), false); // 配った版（家族の練習）には出さない
  assert.equal(sheetEnabled(work([])), true);
  assert.equal(sheetEnabled({ ...work([]), draft: undefined }), false);
});

test('受付を開いた瞬間に、開いている欄は閉じる（書きかけは修正票に入れる）・受付中は開かない', () => {
  const ctx = { draft: true, roomOpen: false };
  assert.deepEqual(editorStep(null, { type: 'open', slide: 3 }, ctx), { open: 3, commit: false });
  assert.deepEqual(editorStep(3, { type: 'room' }, { draft: true, roomOpen: true }), { open: null, commit: true });
  assert.deepEqual(editorStep(null, { type: 'open', slide: 3 }, { draft: true, roomOpen: true }), { open: null, commit: false });
  assert.deepEqual(editorStep(null, { type: 'open', slide: 3 }, { draft: false, roomOpen: false }), { open: null, commit: false });
  assert.deepEqual(editorStep(3, { type: 'move' }, ctx), { open: null, commit: true });
  assert.deepEqual(editorStep(3, { type: 'cancel' }, ctx), { open: null, commit: false });
  assert.deepEqual(editorStep(null, { type: 'room' }, ctx), { open: null, commit: false });
});

test('読み直しは練習中だけ・今の枚を保つ（枚数が減ったら最後の枚へ）', () => {
  assert.equal(mayReload({ hasWork: true, roomOpen: false }), true);
  assert.equal(mayReload({ hasWork: true, roomOpen: true }), false);
  assert.equal(mayReload({ hasWork: false, roomOpen: false }), false);
  assert.equal(keepSlide(7, 18), 7);
  assert.equal(keepSlide(18, 15), 15);
  assert.equal(keepSlide(0, 5), 1);
});

// ---------- 段落・枠 ----------

test('段落は1行以上の空行で区切る（空白だけの行も空行）・行末の空白はそろえる', () => {
  assert.deepEqual(paragraphs('一行目\n二行目  \n\n\n> 合図\n \n最後'), ['一行目\n二行目', '> 合図', '最後']);
  assert.deepEqual(paragraphs(''), []);
});

test('画面の文字の欄: 欄の中の改行＝段落内改行・空にした欄は消す・もともと空の段落は残す（決定4）', () => {
  const box = [['行1', '行2'], [''], ['下']];
  const fields = fieldsFromBox(box);
  assert.deepEqual(boxFromFields(fields), box);
  fields[2].text = '';                                   // 文字のある段落を空にした → 消す
  fields.push({ text: '足した\n二行', orig: null });     // 「段落を足す」
  fields.push({ text: '', orig: null });                 // 足して空のまま → 消す
  assert.deepEqual(boxFromFields(fields), [['行1', '行2'], [''], ['足した', '二行']]);
  assert.deepEqual(boxFromFields(fields.map((f) => ({ ...f, text: '' })).filter((f) => f.orig !== '')), []); // 全部消した＝枠を消す
});

// ---------- 差分 → 件（E2） ----------

test('notes は変わった段落ごとに1件。場所は段落の番号', () => {
  const items = diffNotes(4, 'あ\n\nい\n\nう', 'あ\n\nいい\n\nうう');
  assert.deepEqual(items.map((x) => [x.at, x.before, x.after]), [[[2, 2], ['い'], ['いい']], [[3, 3], ['う'], ['うう']]]);
  assert.deepEqual(diffNotes(4, 'あ\n\nい', 'あ\n\nい'), []);
});

test('段落を足したら、直前の変わっていない段落を一緒に運ぶ（先頭なら直後）。消したら新しい文は空', () => {
  assert.deepEqual(diffNotes(1, 'あ\n\nい', 'あ\n\n足す\n\nい').map((x) => [x.at, x.before, x.after]), [[[1, 1], ['あ'], ['あ', '足す']]]);
  assert.deepEqual(diffNotes(1, 'あ\n\nい', '先頭\n\nあ\n\nい').map((x) => [x.at, x.before, x.after]), [[[1, 1], ['あ'], ['先頭', 'あ']]]);
  assert.deepEqual(diffNotes(1, 'あ\n\nい\n\nう', 'あ\n\nう').map((x) => [x.at, x.before, x.after]), [[[2, 2], ['い'], []]]);
  assert.deepEqual(diffNotes(1, 'あ\n\nい\n\nう', 'あ\n\n一つに').map((x) => [x.at, x.before, x.after]), [[[2, 3], ['い', 'う'], ['一つに']]]);
  assert.deepEqual(diffNotes(1, '', '書いた').map((x) => [x.before, x.after]), [[[], ['書いた']]]);
});

test('overlay は変わった枠ごと。場所は文字のある枠の番号。空＝枠を消す', () => {
  const before = [[['上']], [['〜習慣の科学〜']]];
  assert.deepEqual(diffOverlays(1, before, [[['上']], [['〜習慣の', '科学〜']]]), [
    { slide: 1, kind: 'overlay', at: 2, before: [['〜習慣の科学〜']], after: [['〜習慣の', '科学〜']] }]);
  assert.deepEqual(diffOverlays(1, before, [[], [['〜習慣の科学〜']]]).map((x) => [x.at, x.after]), [[1, []]]);
  assert.deepEqual(diffOverlays(1, before, [[['上  ']], [['〜習慣の科学〜']]]), []); // 行末の空白だけの違いは変更でない
});

// ---------- 判定（E10 の表の全マス） ----------

const notesItem = (before, after) => ({ slide: 1, kind: 'notes', at: [1, 1], before, after });
const boxItem = (before, after) => ({ slide: 1, kind: 'overlay', at: 1, before, after });

test('E10 書き換え: 新しい文がある→反映済み／どちらも無い→手を入れて反映／元の文のまま→未反映', () => {
  const x = notesItem(['元の文'], ['新しい文']);
  assert.equal(judge(x, slide(1, 'あ\n\n新しい文')), 'done');
  assert.equal(judge(x, slide(1, 'あ\n\nClaude が整えた文')), 'reworded');
  assert.equal(judge(x, slide(1, 'あ\n\n元の文')), 'pending');
  const b = boxItem([['元']], [['新', '二行']]);
  assert.equal(judge(b, slide(1, '', [[['新', '二行']]])), 'done');
  assert.equal(judge(b, slide(1, '', [[['整えた']]])), 'reworded');
  assert.equal(judge(b, slide(1, '', [[['元']]])), 'pending');
});

test('E10 消した: 元の文が無い→反映済み／ある→未反映（空の新しい文はどこにでも含まれる、で反映済みにしない）', () => {
  assert.equal(judge(notesItem(['消す段落'], []), slide(1, 'あ')), 'done');
  assert.equal(judge(notesItem(['消す段落'], []), slide(1, 'あ\n\n消す段落')), 'pending');
  assert.equal(judge(boxItem([['消す枠']], []), slide(1, '', [])), 'done');
  assert.equal(judge(boxItem([['消す枠']], []), slide(1, '', [[['消す枠']]])), 'pending');
});

test('E10 一致は段落・枠まるごと（短い文が別の段落に含まれても反映済みにしない）・行末の空白はそろえる', () => {
  const x = notesItem(['元の文'], ['はい']);
  assert.equal(judge(x, slide(1, 'はいと言った\n\n元の文')), 'pending');
  assert.equal(judge(x, slide(1, 'はい   \n\nほか')), 'done');
  assert.equal(judge(boxItem([['元']], [['短']]), slide(1, '', [[['短い文']], [['元']]])), 'pending');
  // 複数の段落の件は、同じ段落が続けて現れたときだけ
  const y = notesItem(['い', 'う'], ['いう']);
  assert.equal(judge(y, slide(1, 'い\n\nえ\n\nう')), 'reworded');
  assert.equal(judge(y, slide(1, 'あ\n\nい\n\nう')), 'pending');
});

test('E10 比べるのは同じ枚の中だけ', () => {
  const w = work([slide(1, '別の枚の文'), slide(2, '元の文')]);
  let sheet = setSlideEdits(emptySheet(w.title), w.slides[1], { notes: '新しい文' });
  const w2 = work([slide(1, '新しい文'), slide(2, '元の文')]); // 別の枚に同じ文がある
  const r = reconcile(sheet, w2);
  assert.equal(r.done, 0);
  assert.deepEqual(r.status, ['pending']);
  sheet = r.sheet;
  assert.equal(sheet.items.length, 1);
});

test('読み直し: 反映済みは自動で消し、手を入れて反映は残す。直した件の消えた枚のひとことも消す', () => {
  const w = work([slide(1, 'あ\n\nい', [[['題']]]), slide(2, 'う'), slide(3, 'え')]);
  let s = emptySheet(w.title);
  s = setSlideEdits(s, w.slides[0], { notes: 'あ\n\nいい', overlays: [[['題', '二行']]], comment: '読みやすく' });
  s = setSlideEdits(s, w.slides[1], { notes: 'うう' });
  s = setSlideEdits(s, w.slides[2], { comment: '枠を足して' });     // 文を直さないひとこと
  assert.equal(s.items.length, 3);
  const w2 = work([slide(1, 'あ\n\nいい', [[['題', '二行']]]), slide(2, 'Claude が整えた'), slide(3, 'え')]);
  const r = reconcile(s, w2);
  assert.equal(r.done, 2);
  assert.deepEqual(r.sheet.items.map((x) => x.slide), [2]);
  assert.deepEqual(r.status, ['reworded']);
  assert.deepEqual(r.sheet.comments, { 3: '枠を足して' });
  // 手を入れて反映した件は、直す欄を閉じ直しても残る（練習した人が見て消す）
  const again = setSlideEdits(r.sheet, w2.slides[1], { notes: 'Claude が整えた' });
  assert.equal(again.items.length, 1);
  assert.equal(removeItem(again, 0).items.length, 0);
});

// ---------- 直した後の文を出す（E6） ----------

test('直した後の文を台本の欄に出す。消した枠は null・印を付ける', () => {
  const s0 = slide(1, 'あ\n\nい', [[['上']], [['下']]]);
  const s = setSlideEdits(emptySheet('t'), s0, { notes: 'あ\n\n足す\n\nい', overlays: [[], [['下', '二']]] });
  const a = applySheet(s, s0);
  assert.equal(a.notes, 'あ\n\n足す\n\nい');
  assert.deepEqual(a.overlays, [null, [['下', '二']]]);
  assert.equal(a.edited.notes, true);
  assert.deepEqual([...a.edited.boxes].sort(), [1, 2]);
  const none = applySheet(emptySheet('t'), s0);
  assert.equal(none.notes, 'あ\n\nい');                // 直していなければ元の notes のまま（改行もそのまま）
  assert.equal(none.edited.notes, false);
  // 直す欄をもう一度閉じると、直した後の文を元に件を作り直す（重ならない）
  const s2 = setSlideEdits(s, s0, { notes: a.notes, overlays: [[], [['下', '二']]] });
  assert.deepEqual(s2.items, s.items);
});

// ---------- Markdown（F2） ----------

test('囲みの ` は、本文中で最も長い並びより1つ多い（本文に ``` があっても壊れない）', () => {
  assert.equal(fence('ふつう'), '```\nふつう\n```');
  assert.equal(fence('a ``` b'), '````\na ``` b\n````');
  assert.equal(fence('`````'), '``````\n`````\n``````');
});

test('修正票の Markdown: 見出しが1件・元と新は囲み・overlay の段落は空行・ひとことは枚の最後の件に', () => {
  const s0 = slide(4, 'あ\n\nい', [[['〜習慣の科学〜']]]);
  let s = setSlideEdits(emptySheet('小さな薪を、毎日くべる'), s0,
    { notes: 'あ\n\nいい', overlays: [[['〜習慣の', '科学〜'], ['二段落目']]], comment: 'ここは ``` を含む' });
  s = setSlideEdits(s, slide(6, ''), { comment: '枠を足したい' });
  const md = sheetMarkdown(s, new Date(2026, 9, 25, 21, 4));
  assert.equal(md, [
    '# Correction sheet: 小さな薪を、毎日くべる (2026-10-25 21:04)',
    '',
    '## [Slide 4] notes 2',
    '### Before', '```', 'い', '```',
    '### After', '```', 'いい', '```',
    '',
    '## [Slide 4] overlay 1',
    '### Before', '```', '〜習慣の科学〜', '```',
    '### After', '```', '〜習慣の\n科学〜\n\n二段落目', '```',
    'Comment: ここは ``` を含む',
    '',
    '## [Slide 6] comment',
    'Comment: 枠を足したい',
    '',
  ].join('\n'));
  // 手を入れて反映した件は書かない
  assert.ok(!sheetMarkdown(s, new Date(), new Set([0])).includes('notes 2'));
  assert.match(sheetName('小さな薪', new Date(2026, 9, 25, 21, 4)), /^小さな薪-corrections-20261025-2104\.md$/);
});

test('段落の範囲は notes P-Q と書く', () => {
  const s = setSlideEdits(emptySheet('t'), slide(1, 'あ\n\nい\n\nう'), { notes: 'あ\n\n一つに' });
  assert.match(sheetMarkdown(s, new Date()), /## \[Slide 1\] notes 2-3\n### Before\n```\nい\n\nう\n```/);
});

// ---------- 保存の形（E5） ----------

test('保存した修正票は作品の題で引き、形が違えば空の票にする', () => {
  const s = setSlideEdits(emptySheet('題'), slide(1, 'あ'), { notes: 'い', comment: 'ひとこと' });
  const back = readSheet(JSON.stringify(s), '題');
  assert.deepEqual(back, s);
  assert.ok(isEmpty(readSheet(JSON.stringify(s), '別の題')));
  assert.ok(isEmpty(readSheet('壊れた', '題')));
  assert.ok(isEmpty(readSheet(JSON.stringify({ ...s, v: 99 }), '題')));
  assert.equal(readSheet(JSON.stringify({ ...s, items: [{ slide: 1, kind: 'x' }, ...s.items] }), '題').items.length, 1);
  assert.equal(storageKey('題'), 'dk-corrections:題');
});

// ---------- エンディング動画のコマ（seat。§6 ending seat N・M1・M6） ----------

const seats = [
  { n: 1, from: 2, to: 8, label: 'photos/a.jpg' },
  { n: 2, from: 8, to: 14, label: 'photos/b.jpg', pin: 'the chorus' },
];
const endingSlide = (labels = ['photos/a.jpg', 'photos/b.jpg']) => ({
  number: 4, title: 'End', picture: null, notes: 'Play it.',
  cues: [{ type: 'video', file: 'videos/clip.mp4' },
    { type: 'video', file: 'videos/ending.mp4', role: 'ending', seats: seats.map((s, i) => ({ ...s, label: labels[i] })) }],
});
const FILE = { size: 1000, modified: 111 };

test('止めた位置のコマを指すと、その枚の何本目の動画の何番のコマかが入る・同じコマは1件にまとめる', () => {
  let sh = pointSeat(emptySheet('T'), endingSlide(), 2, seats, 9.04, FILE, '  too   dark ');
  assert.deepEqual(sh.items, [{ slide: 4, kind: 'seat', at: 2, video: 2, time: 9, label: 'photos/b.jpg', pin: 'the chorus', file: FILE, comment: 'too dark' }]);
  sh = pointSeat(sh, endingSlide(), 2, seats, 10, FILE, 'another morning');
  assert.equal(sh.items.length, 1);
  assert.equal(sh.items[0].comment, 'another morning');
  assert.equal(pointSeat(sh, endingSlide(), 2, seats, 1.5, FILE), sh, 'コマの外（前の映像）では何も入らない');
});

test('コマの件は Markdown に At・Label・Pin・Comment で書く（文の件・その枚のひとことと並ぶ）', () => {
  let sh = setSlideEdits(emptySheet('T'), endingSlide(), { notes: 'Play it now.', comment: 'slower' });
  sh = pointSeat(sh, endingSlide(), 2, seats, 3.25, FILE);
  assert.equal(clock(83.25), '1:23.3');
  assert.equal(clock(3), '0:03.0');
  const md = sheetMarkdown(sh, new Date(2026, 9, 26, 10, 0));
  assert.equal(md, [
    '# Correction sheet: T (2026-10-26 10:00)', '',
    '## [Slide 4] notes 1', '### Before', '```', 'Play it.', '```', '### After', '```', 'Play it now.', '```', 'Comment: slower', '',
    '## [Slide 4] ending seat 1', 'At 0:03.3', 'Label photos/a.jpg', '',
  ].join('\n'));
  assert.deepEqual(seatLines({ time: 9, label: 'b', pin: 'p', comment: 'c' }), ['At 0:09.0', 'Label b', 'Pin p', 'Comment: c']);
});

test('ひとことだけの枚にコマの件があっても、ひとことは comment の見出しで残る', () => {
  let sh = setSlideEdits(emptySheet('T'), endingSlide(), { notes: 'Play it.', comment: 'music too loud' });
  sh = pointSeat(sh, endingSlide(), 2, seats, 3, FILE);
  const md = sheetMarkdown(sh, new Date(2026, 9, 26, 10, 0));
  assert.match(md, /## \[Slide 4\] comment\nComment: music too loud\n\n## \[Slide 4\] ending seat 1/);
});

test('直す欄を閉じても、指したコマは消えない', () => {
  let sh = pointSeat(emptySheet('T'), endingSlide(), 2, seats, 3, FILE);
  sh = setSlideEdits(sh, endingSlide(), { notes: 'Play it.' });
  assert.equal(sh.items.length, 1);
  assert.equal(applySheet(sh, endingSlide()).notes, 'Play it.', 'コマの件は台本に当てない');
});

test('読み直し: 写真の名前か動画のファイルが変わったら「変わった」・自分では消さない・変わっていなければ未反映', () => {
  const sh = pointSeat(emptySheet('T'), endingSlide(), 2, seats, 3, FILE);
  const x = sh.items[0];
  assert.equal(judge(x, endingSlide(), () => FILE), 'pending');
  assert.equal(judge(x, endingSlide(), () => null), 'pending', '動画が手元に無ければ写真の名前だけで見る');
  assert.equal(judge(x, endingSlide(['photos/new.jpg', 'photos/b.jpg']), () => FILE), 'changed');
  assert.equal(judge(x, endingSlide(), () => ({ size: 1000, modified: 222 })), 'changed');
  const w = { title: 'T', slides: [1, 2, 3].map((n) => slide(n, '')).concat([endingSlide(['photos/new.jpg', 'photos/b.jpg'])]) };
  const rc = reconcile(sh, w, () => FILE);
  assert.equal(rc.done, 0);
  assert.deepEqual(rc.status, ['changed']);
  assert.equal(rc.sheet.items.length, 1);
  const gone = reconcile(sh, { title: 'T', slides: [slide(1, '')] });
  assert.deepEqual(gone.status, ['changed'], '枚が無くなった');
});

test('保存したコマの件を読み戻す・形の違う件は捨てる', () => {
  const sh = pointSeat(emptySheet('T'), endingSlide(), 2, seats, 9, FILE, 'x');
  assert.deepEqual(readSheet(JSON.stringify(sh), 'T'), sh);
  const bad = { ...sh, items: [{ ...sh.items[0], video: 'two' }, { ...sh.items[0], file: { size: 1 } }] };
  assert.deepEqual(readSheet(JSON.stringify(bad), 'T').items, []);
});

// ---------- 上演中の動画の区間（video K。§6・M3・M6） ----------

const two = [{ start: 82, dur: 74 }, { start: 278, dur: 105 }];
const showSlide = (segs = two, extra = {}) => ({
  number: 8, title: 'Jump', picture: 'pictures/08.jpg', notes: 'Watch.',
  cues: [{ type: 'bgm-stop' }, { type: 'video', file: 'videos/a.mp4', ...extra },
    { type: 'video', file: 'videos/b.mp4', ...(segs ? { source_segments: segs } : {}) }],
});

test('区間の端を入れると、その枚の何本目の動画か・元の動画での秒が入る（区間2つ・境目）', () => {
  let sh = markCut(emptySheet('T'), showSlide(), 2, 'from', 10.04, FILE);
  assert.deepEqual(sh.items, [{ slide: 8, kind: 'video', at: 2, from: 10, fromSource: 92, segments: two, file: FILE }]);
  sh = markCut(sh, showSlide(), 2, 'to', 74, FILE, '  stop  at the board ');
  assert.equal(sh.items.length, 1, '同じ動画は1件');
  assert.deepEqual(sh.items[0], { slide: 8, kind: 'video', at: 2, from: 10, fromSource: 92, to: 74, toSource: 156, segments: two, file: FILE, comment: 'stop at the board' },
    '終わりが区間の境目ちょうどなら、前の区間の終わり（後ろの頭ではない）');
  sh = markCut(sh, showSlide(), 2, 'from', 74, FILE);
  assert.equal(sh.items[0].to, undefined, '開始が終わり以降になったら、終わりを外す');
  assert.equal(sh.items[0].fromSource, 278, '開始が境目ちょうどなら後ろの区間の頭');
  assert.equal(sh.items[0].comment, 'stop at the board', 'ひとことを渡さなければ前のを保つ');
  sh = markCut(sh, showSlide(), 2, 'to', 150.55, FILE, '');
  assert.deepEqual([sh.items[0].from, sh.items[0].to, sh.items[0].toSource, sh.items[0].comment], [74, 150.6, 354.6, undefined]);
});

test('元の区間が無い動画（家族の作品）は動画の中の秒だけ・エンディング動画と無い番号は入らない', () => {
  let sh = markCut(emptySheet('T'), showSlide(), 1, 'to', 3, null);
  assert.deepEqual(sh.items, [{ slide: 8, kind: 'video', at: 1, to: 3 }]);
  const ending = showSlide(two, { role: 'ending', seats: [{ n: 1, from: 0, to: 5 }] });
  assert.equal(markCut(sh, ending, 1, 'from', 1, FILE), sh);
  assert.equal(markCut(sh, showSlide(), 3, 'from', 1, FILE), sh);
  assert.equal(markCut(sh, showSlide(), 2, 'middle', 1, FILE), sh);
});

test('区間の件は Markdown に From・To（source）・Comment で書く・コマの件より前', () => {
  let sh = markCut(emptySheet('T'), showSlide(), 2, 'from', 12.5, FILE);
  sh = markCut(sh, showSlide(), 2, 'to', 100, FILE, 'after the interview');
  sh = markCut(sh, showSlide(), 1, 'from', 3, FILE);
  sh = { ...sh, comments: { 8: 'louder' } };
  assert.equal(sheetMarkdown(sh, new Date(2026, 9, 26, 10, 0)), [
    '# Correction sheet: T (2026-10-26 10:00)', '',
    '## [Slide 8] comment', 'Comment: louder', '',
    '## [Slide 8] video 1', 'From 0:03.0', '',
    '## [Slide 8] video 2', 'From 0:12.5 (source 1:34.5)', 'To 1:40.0 (source 5:04.0)', 'Comment: after the interview', '',
  ].join('\n'));
  assert.deepEqual(cutLines({ to: 61 }), ['To 1:01.0']);
  assert.equal(place(sh.items[1]), 'video 2');
  assert.deepEqual(mediaLines({ kind: 'seat', time: 1 }), ['At 0:01.0']);
});

test('直す欄を閉じても区間の件は残り、台本には当てない', () => {
  let sh = markCut(emptySheet('T'), showSlide(), 2, 'from', 12.5, FILE);
  sh = setSlideEdits(sh, showSlide(), { notes: 'Watch it.' });
  assert.deepEqual(sh.items.map((x) => x.kind), ['notes', 'video']);
  assert.equal(applySheet(sh, showSlide()).notes, 'Watch it.');
});

test('読み直し: 動画のファイルか元の区間が変わったら「変わった」・自分では消さない', () => {
  const sh = markCut(emptySheet('T'), showSlide(), 2, 'from', 12.5, FILE);
  const x = sh.items[0];
  assert.equal(judge(x, showSlide(), () => FILE), 'pending');
  assert.equal(judge(x, showSlide(), () => null), 'pending', '動画が手元に無ければ元の区間だけで見る');
  assert.equal(judge(x, showSlide(), () => ({ size: 999, modified: 111 })), 'changed');
  assert.equal(judge(x, showSlide([{ start: 90, dur: 66 }, { start: 278, dur: 105 }]), () => null), 'changed', '区間を直した');
  assert.equal(judge(x, showSlide(null), () => FILE), 'changed', '元の区間が無くなった');
  assert.equal(judge(x, { ...showSlide(), cues: [] }), 'changed', 'その動画が無い');
  assert.equal(videoOf(x), 2);
  const rc = reconcile(sh, { title: 'T', slides: [] });
  assert.deepEqual([rc.done, rc.status, rc.sheet.items.length], [0, ['changed'], 1]);
});

test('保存した区間の件を読み戻す・形の違う件は捨てる', () => {
  let sh = markCut(emptySheet('T'), showSlide(), 2, 'from', 12.5, FILE, 'x');
  sh = markCut(sh, showSlide(), 1, 'to', 2, null);
  assert.deepEqual(readSheet(JSON.stringify(sh), 'T'), sh);
  const x = sh.items[0];
  const bad = [{ ...x, at: '2' }, { ...x, from: '0:12.5' }, { slide: 8, kind: 'video', at: 1 }, { ...x, segments: [{ start: 1 }] }, { ...x, file: { size: 1 } }];
  assert.deepEqual(readSheet(JSON.stringify({ ...sh, items: bad }), 'T').items, []);
});

// ---------- 絵の作り直し（picture。§6・M4・M6） ----------

const picSlide = (picture = 'pictures/03.png') => ({ number: 3, title: 'Morning', picture, notes: 'The sun.', overlays: [], cues: [] });

test('絵の作り直しは文が必須・1枚に1件（書き直せば置き換える）・絵のパスとファイルを持つ', () => {
  const empty = emptySheet('T');
  assert.equal(askPicture(empty, picSlide(), FILE, ''), empty, '文が無ければ入らない');
  assert.equal(askPicture(empty, picSlide(), FILE, '   '), empty, '空白だけの文も入らない');
  assert.equal(askPicture(empty, picSlide(null), FILE, 'darker'), empty, '絵の無い枚には入らない');
  let sh = askPicture(empty, picSlide(), FILE, '  the lamp   should be dark ');
  assert.deepEqual(sh.items, [{ slide: 3, kind: 'picture', path: 'pictures/03.png', comment: 'the lamp should be dark', file: FILE }]);
  sh = askPicture(sh, picSlide(), FILE, 'no gulls');
  assert.equal(sh.items.length, 1);
  assert.equal(sh.items[0].comment, 'no gulls');
  assert.equal(videoOf(sh.items[0]), null, '絵の件は動画を指さない');
});

test('絵の件は Markdown に Comment だけで書く（パス・ファイルの見分けは書かない）・文の件の後、動画の件の前', () => {
  let sh = setSlideEdits(emptySheet('T'), picSlide(), { notes: 'The sun rose.', comment: 'slower' });
  sh = askPicture(sh, picSlide(), FILE, 'the lamp should be dark');
  sh = markCut(sh, { ...picSlide(), cues: [{ type: 'video', file: 'videos/v.mp4' }] }, 1, 'from', 2, FILE);
  const md = sheetMarkdown(sh, new Date(2026, 9, 26, 10, 0));
  assert.equal(md, [
    '# Correction sheet: T (2026-10-26 10:00)', '',
    '## [Slide 3] notes 1', '### Before', '```', 'The sun.', '```', '### After', '```', 'The sun rose.', '```', 'Comment: slower', '',
    '## [Slide 3] picture', 'Comment: the lamp should be dark', '',
    '## [Slide 3] video 1', 'From 0:02.0', '',
  ].join('\n'));
  assert.equal(place(sh.items[1]), 'picture');
  assert.deepEqual(pictureLines({ comment: 'c' }), ['Comment: c']);
  assert.deepEqual(mediaLines({ kind: 'picture', comment: 'c' }), ['Comment: c']);
});

test('ひとことだけの枚に絵の件があっても、ひとことは comment の見出しで残る・直す欄を閉じても絵の件は残る', () => {
  let sh = askPicture(emptySheet('T'), picSlide(), FILE, 'darker');
  sh = setSlideEdits(sh, picSlide(), { notes: 'The sun.', comment: 'too fast' });
  assert.deepEqual(sh.items.map((x) => x.kind), ['picture']);
  assert.match(sheetMarkdown(sh, new Date(2026, 9, 26, 10, 0)), /## \[Slide 3\] comment\nComment: too fast\n\n## \[Slide 3\] picture\nComment: darker/);
  assert.equal(applySheet(sh, picSlide()).notes, 'The sun.', '絵の件は台本に当てない');
});

test('読み直し: 絵のパスかファイルが変わったら「変わった」・候補を作っただけ（絵が同じ）なら未反映のまま・自分では消さない', () => {
  const sh = askPicture(emptySheet('T'), picSlide(), FILE, 'darker');
  const x = sh.items[0];
  assert.equal(judge(x, picSlide(), () => FILE), 'pending', '候補が増えただけでは絵は同じ');
  assert.equal(judge(x, picSlide(), () => null), 'pending', '絵が手元に無ければパスだけで見る');
  assert.equal(judge(x, picSlide(), () => ({ size: 1000, modified: 222 })), 'changed', '--use で入れ替えた（同じ名前の新しいファイル）');
  assert.equal(judge(x, picSlide(), () => ({ size: 2000, modified: 111 })), 'changed');
  assert.equal(judge(x, picSlide('pictures/03.jpg'), () => FILE), 'changed', '絵のパスが変わった（写真に差し替えた）');
  assert.equal(judge(x, picSlide(null)), 'changed', '絵が無くなった');
  const w = { title: 'T', slides: [slide(1, ''), slide(2, ''), picSlide()] };
  const rc = reconcile(sh, w, () => ({ size: 1, modified: 1 }));
  assert.deepEqual([rc.done, rc.status, rc.sheet.items.length], [0, ['changed'], 1]);
  assert.deepEqual(reconcile(sh, w, () => FILE).status, ['pending']);
  assert.deepEqual(reconcile(sh, { title: 'T', slides: [slide(1, '')] }).status, ['changed'], '枚が無くなった');
});

test('文字を載せた枚の絵の件は、組み立ての元の絵で見る: 組み立て直しただけでは未反映のまま（Issue #5）', () => {
  const built = { ...picSlide('pictures/_built/03.jpg'), picture_source: 'pictures/03.png' };
  const sh = askPicture(emptySheet('T'), built, FILE, 'no white margin');
  const x = sh.items[0];
  assert.equal(x.path, 'pictures/03.png', '元の絵のパスを持つ');
  assert.equal(judge(x, built, () => FILE), 'pending', '組み立て直しても元の絵は同じ');
  assert.equal(judge(x, built, () => null), 'pending', '元の絵が手元に無ければパスだけで見る');
  assert.equal(judge(x, built, () => ({ size: 1000, modified: 222 })), 'changed', '元の絵を同じ名前で入れ替えた');
  assert.equal(judge(x, { ...built, picture_source: 'pictures/03.jpg' }, () => FILE), 'changed', '[Picture] が別の絵になった');
  const use = choosePicture(emptySheet('T'), built, FILE, 'pictures/_candidates/03-1.png').items[0];
  assert.equal(use.path, 'pictures/03.png');
  assert.equal(judge(use, built, () => ({ size: 1000, modified: 222, useLeft: false })), 'done', '--use で差し替えた');
  assert.equal(judge(use, built, () => ({ ...FILE, useLeft: true })), 'pending');
});

test('元の絵を持つ前の件（組み立てた絵のパスと見分け）は、パスだけで見る: 組み立て直しで「変わった」にしない', () => {
  const built = { ...picSlide('pictures/_built/03.jpg'), picture_source: 'pictures/03.png' };
  const old = askPicture(emptySheet('T'), picSlide('pictures/_built/03.jpg'), FILE, 'darker').items[0];
  assert.equal(old.path, 'pictures/_built/03.jpg');
  assert.equal(judge(old, built, () => ({ size: 5, modified: 999 })), 'pending');
  const oldUse = choosePicture(emptySheet('T'), picSlide('pictures/_built/03.jpg'), FILE, 'pictures/_candidates/03-1.png').items[0];
  assert.equal(judge(oldUse, built, () => ({ size: 5, modified: 999, useLeft: false })), 'done', '選んだ候補が片づいた');
  assert.equal(judge(old, { ...built, picture: 'pictures/_built/03.png' }, () => FILE), 'changed', '組み立てた絵のパスも変わった');
});

test('保存した絵の件を読み戻す・形の違う件（文が無い・パスが無い・見分けが壊れた）は捨てる', () => {
  let sh = askPicture(emptySheet('T'), picSlide(), FILE, 'darker');
  sh = askPicture(sh, { ...picSlide(), number: 2 }, null, 'brighter');
  assert.deepEqual(readSheet(JSON.stringify(sh), 'T'), sh);
  const x = sh.items[1];
  const bad = [{ ...x, comment: '' }, { ...x, comment: undefined }, { ...x, path: '' }, { ...x, path: 3 }, { ...x, file: { size: 1 } }];
  assert.deepEqual(readSheet(JSON.stringify({ ...sh, items: bad }), 'T').items, []);
});

test('修正票のボタンの数: ひとことも、書いたときの作品のままなら未反映・作品が変わったら見て消す（2026-10-26）', () => {
  const w1 = work([slide(1, 'a'), slide(2, 'c'), slide(3, 'd')]);
  const sig1 = workSig(w1);
  let sh = setSlideEdits(emptySheet('T'), slide(1, 'a'), { notes: 'b', comment: 'with an edit' }, sig1);   // 文の件＋ひとこと（ひとことは件と一緒）
  sh = setSlideEdits(sh, slide(2, 'c'), { notes: 'c', comment: 'only a comment' }, sig1);               // ひとことだけ
  sh = setSlideEdits(sh, slide(3, 'd'), { notes: 'e' }, sig1);
  sh = askPicture(sh, picSlide(), FILE, 'darker');
  const st = { 1: 'pending', 3: 'reworded' };
  const stOf = (x) => (x.kind === 'picture' ? 'changed' : st[x.slide]);
  assert.deepEqual(sheetCounts(sh, stOf, sig1), { pending: 2, look: 2, done: 0 }, '書いたばかりのひとことは未反映');
  const sig2 = workSig(work([slide(1, 'b'), slide(2, 'c'), slide(3, 'd')]));
  assert.notEqual(sig1, sig2);
  assert.equal(commentStatus(sh, 2, sig2), 'changed');
  // 読み直し（reconcile）は、件の残る1枚目のひとことを sig2 に付け直す（2026-10-29。ここでは件の判定を stOf で決めているので手で）
  sh = { ...sh, commentAt: { ...sh.commentAt, 1: sig2 } };
  assert.deepEqual(sheetCounts(sh, stOf, sig2), { pending: 1, look: 3, done: 0 }, '作品が変わったら見て消す（自分では消さない）');
  assert.ok(sh.comments[2], 'ひとことは残る');
  assert.deepEqual(sheetCounts(emptySheet('T'), () => 'pending', sig1), { pending: 0, look: 0, done: 0 });
});

test('ひとことのしるし: 書き替えたときだけ付け直す・消すと一緒に消える・保存して読み戻す・しるしの無い（前からの）ひとことは見て消す', () => {
  const sig1 = 'aaaaaaaa', sig2 = 'bbbbbbbb';
  let sh = setSlideEdits(emptySheet('T'), slide(2, 'c'), { notes: 'c', comment: 'louder' }, sig1);
  assert.equal(sh.commentAt[2], sig1);
  sh = setSlideEdits(sh, slide(2, 'c'), { notes: 'c', comment: 'louder' }, sig2);
  assert.equal(sh.commentAt[2], sig1, '同じひとことのまま欄を閉じても、書いたときのしるしのまま');
  sh = setSlideEdits(sh, slide(2, 'c'), { notes: 'c', comment: 'much louder' }, sig2);
  assert.equal(sh.commentAt[2], sig2, '書き替えたら、いまの作品のしるし');
  assert.deepEqual(readSheet(JSON.stringify(sh), 'T'), sh);
  assert.deepEqual(readSheet(JSON.stringify({ ...sh, commentAt: { 2: 'not-a-sig', 9: sig1 } }), 'T').commentAt, {});
  const old = { ...sh, commentAt: {} };
  assert.equal(commentStatus(old, 2, sig2), 'changed', 'しるしの無いひとこと');
  sh = removeComment(sh, 2);
  assert.deepEqual([sh.comments, sh.commentAt], [{}, {}]);
});

test('前回のひとこと: 作品が変わったあと、その枚に足した直しの理由にしない（2026-10-29 実際の作品で）', () => {
  const w1 = work([slide(1, 'a'), slide(2, 'b\n\nc')]);
  const sig1 = workSig(w1);
  // 前回: 2枚目にひとことだけ、1枚目に直し＋ひとこと
  let sh = setSlideEdits(emptySheet('小さな薪'), slide(2, 'b\n\nc'), { notes: 'b\n\nc', comment: 'BGM が鳴らない' }, sig1);
  sh = setSlideEdits(sh, slide(1, 'a'), { notes: 'a2', comment: 'もっと短く' }, sig1);
  // 作品を書き出し直した（1枚目の直しはまだ入っていない）→ 読み直す
  const w2 = work([slide(1, 'a'), slide(2, 'b\n\nc'), slide(3, 'd')]);
  const sig2 = workSig(w2);
  const rc = reconcile(sh, w2);
  sh = rc.sheet;
  assert.equal(rc.resigned, 1, '件の残る枚のひとことは、いまの作品のしるしに付け直す');
  assert.equal(isOldComment(sh, 1, sig2), false, '件の理由としてまだ生きている');
  assert.equal(isOldComment(sh, 2, sig2), true, 'ひとことだけの枚は前回のひとこと');
  // 今回: 2枚目の語りを直す。ひとことの欄には触れない（undefined）
  sh = setSlideEdits(sh, slide(2, 'b\n\nc'), { notes: 'b\n\nc2', comment: undefined }, sig2);
  assert.equal(sh.comments[2], 'BGM が鳴らない', '触れていなければ消さない（見て消すのは練習した人）');
  assert.equal(isOldComment(sh, 2, sig2), true, '欄を閉じても前回のまま');
  const md = sheetMarkdown(sh, new Date(2026, 9, 29, 17, 0), new Set(), sig2);
  assert.ok(!md.includes('BGM が鳴らない'), '修正票に書かない');
  assert.match(md, /notes 1\n### Before\n```\na\n```\n### After\n```\na2\n```\nComment: もっと短く/);
  assert.match(md, /## \[Slide 2\] notes 2/);
  assert.ok(sheetMarkdown(sh, new Date()).includes('BGM が鳴らない'), 'sig を渡さなければ従来どおり');
  // 一覧: 前回のひとことは件に添えず「見て消す」のひとことの行に
  const g = sheetGroups(sh, () => 'pending', sig2);
  assert.deepEqual(g.look.map((r) => [r.kind, r.slide]), [['comment', 2]]);
  assert.deepEqual(g.pending.map((r) => [r.kind, r.slide]), [['item', 1], ['item', 2]]);
  // 新しく書けば置き換わり、今回の直しの理由になる
  sh = setSlideEdits(sh, slide(2, 'b\n\nc'), { notes: 'b\n\nc2', comment: '間を空ける' }, sig2);
  assert.equal(isOldComment(sh, 2, sig2), false);
  assert.match(sheetMarkdown(sh, new Date(), new Set(), sig2), /c2\n```\nComment: 間を空ける/);
});

// ---------- 絵の候補から選ぶ（picture の Use。§6） ----------

const USE = 'pictures/_candidates/03-2.png';

test('候補から選ぶ: Use を持つ絵の件（文は任意）・作り直しの頼みを置き換える・1枚に1件', () => {
  const empty = emptySheet('T');
  assert.equal(choosePicture(empty, picSlide(), FILE, ''), empty, '選んだ候補が無ければ入らない');
  assert.equal(choosePicture(empty, picSlide(null), FILE, USE), empty, '絵の無い枚には入らない');
  let sh = askPicture(empty, picSlide(), FILE, 'darker');
  sh = choosePicture(sh, picSlide(), FILE, USE);
  assert.deepEqual(sh.items, [{ slide: 3, kind: 'picture', path: 'pictures/03.png', use: USE, file: FILE }]);
  sh = choosePicture(sh, picSlide(), FILE, 'pictures/_candidates/03-1.png', ' a bit  darker ');
  assert.deepEqual([sh.items.length, sh.items[0].use, sh.items[0].comment], [1, 'pictures/_candidates/03-1.png', 'a bit darker']);
  sh = askPicture(sh, picSlide(), FILE, 'none of these: no gulls');
  assert.deepEqual(sh.items, [{ slide: 3, kind: 'picture', path: 'pictures/03.png', comment: 'none of these: no gulls', file: FILE }], 'どれもちがう→頼みに戻る');
});

test('候補から選んだ件の Markdown: Use の行（ひとことがあれば Comment も）', () => {
  const sh = choosePicture(emptySheet('T'), picSlide(), FILE, USE);
  assert.equal(sheetMarkdown(sh, new Date(2026, 9, 29, 20, 0)),
    ['# Correction sheet: T (2026-10-29 20:00)', '', '## [Slide 3] picture', `Use ${USE}`, ''].join('\n'));
  assert.deepEqual(pictureLines({ use: USE, comment: 'c' }), [`Use ${USE}`, 'Comment: c']);
  assert.deepEqual(mediaLines({ kind: 'picture', use: USE }), [`Use ${USE}`]);
});

test('候補から選んだ件の判定: 絵が変わり候補が無くなった→反映済み（消える）・候補が残る→変わった・絵が同じ→未反映', () => {
  const x = choosePicture(emptySheet('T'), picSlide(), FILE, USE).items[0];
  const NEW = { size: 3000, modified: 333 };
  assert.equal(judge(x, picSlide(), () => ({ ...FILE, useLeft: true })), 'pending', 'まだ --use していない');
  assert.equal(judge(x, picSlide(), () => ({ ...NEW, useLeft: false })), 'done', '--use で差し替えた');
  assert.equal(judge(x, picSlide(), () => ({ ...NEW, useLeft: true })), 'changed', '絵は変わったが、選んだ候補は残っている');
  assert.equal(judge(x, picSlide(), () => FILE), 'pending', 'useLeft が分からず絵も同じ');
  assert.equal(judge(x, picSlide(null)), 'changed', '絵が無くなった（見分けが無い）');
  const w = { title: 'T', slides: [slide(1, ''), slide(2, ''), picSlide()] };
  const rc = reconcile({ ...emptySheet('T'), items: [x] }, w, () => ({ ...NEW, useLeft: false }));
  assert.deepEqual([rc.done, rc.sheet.items.length], [1, 0]);
});

test('候補から選んだ件を読み戻す（Use だけでもよい）・Use も文も無い件は捨てる', () => {
  const sh = choosePicture(emptySheet('T'), picSlide(), FILE, USE);
  assert.deepEqual(readSheet(JSON.stringify(sh), 'T').items, sh.items);
  const bad = { ...sh, items: [{ slide: 3, kind: 'picture', path: 'pictures/03.png' }, { slide: 3, kind: 'picture', path: 'pictures/03.png', use: '' }] };
  assert.deepEqual(readSheet(JSON.stringify(bad), 'T').items, []);
});

// ---------- リンクの動画の音量（video K の Volume。§6） ----------

const TED = 'https://www.youtube.com/watch?v=8KkKuTCFvzI';
const linkSlide = (volume) => ({ number: 5, title: 'Talk', picture: null, notes: 'Listen.', overlays: [], cues: [
  { type: 'video', file: 'videos/a.mp4' },
  { type: 'video', url: TED, start: 351, end: 369, ...(volume === undefined ? {} : { volume }) },
] });

test('音量: 練習で決めた値を video K の件に入れる・台本の値に戻したら件を消す・リンクの動画だけ', () => {
  let sh = setLinkVolume(emptySheet('T'), linkSlide(), 2, -6);
  assert.deepEqual(sh.items, [{ slide: 5, kind: 'volume', at: 2, db: -6, was: 0 }]);
  assert.equal(linkVolumeNow(sh, linkSlide(), 2), -6);
  sh = setLinkVolume(sh, linkSlide(), 2, -8, '  louder than  the others ');
  assert.deepEqual(sh.items, [{ slide: 5, kind: 'volume', at: 2, db: -8, was: 0, comment: 'louder than the others' }]);
  sh = setLinkVolume(sh, linkSlide(), 2, -10);
  assert.equal(sh.items[0].comment, 'louder than the others', 'ひとことは保つ');
  assert.deepEqual(setLinkVolume(sh, linkSlide(), 2, 0).items, [], '台本の値に戻した');
  assert.equal(linkVolumeNow(emptySheet('T'), linkSlide(-4), 2), -4, '件が無ければ台本の値');
  assert.equal(setLinkVolume(sh, linkSlide(), 1, -6), sh, 'ファイルの動画には付けない');
  assert.equal(setLinkVolume(sh, linkSlide(), 3, -6), sh, '動画の無い番号');
  assert.equal(setLinkVolume(sh, linkSlide(), 2, 2), sh, '元より大きくはできない');
  assert.equal(setLinkVolume(sh, linkSlide(), 2, -42), sh);
});

test('音量: Markdown は ## [Slide N] video K と Volume <値> (was <台本の値>)', () => {
  let sh = setLinkVolume(emptySheet('T'), linkSlide(-4), 2, -10, 'drowns the narration');
  sh = markCut(sh, { ...linkSlide(), cues: [{ type: 'video', file: 'videos/a.mp4' }] }, 1, 'from', 3, FILE);
  assert.equal(sheetMarkdown(sh, new Date(2026, 10, 10, 10, 0)), [
    '# Correction sheet: T (2026-11-10 10:00)', '',
    '## [Slide 5] video 1', 'From 0:03.0', '',
    '## [Slide 5] video 2', 'Volume -10dB (was -4dB)', 'Comment: drowns the narration', '',
  ].join('\n'));
  assert.deepEqual(volumeLines({ db: -7.5, was: 0 }), ['Volume -7.5dB (was 0dB)']);
  assert.equal(dbText(-0), '0dB');
  assert.equal(videoOf(sh.items[1]), 2);
});

test('音量: 読み直して台本がその値なら反映済み・前の値なら未反映・ほかの値かリンクでなくなったら「変わった」', () => {
  const sh = setLinkVolume(emptySheet('T'), linkSlide(), 2, -6);
  const x = sh.items[0];
  assert.equal(judge(x, linkSlide(-6)), 'done');
  assert.equal(judge(x, linkSlide()), 'pending');
  assert.equal(judge(x, linkSlide(-3)), 'changed');
  assert.equal(judge(x, { ...linkSlide(), cues: [{ type: 'video', file: 'videos/a.mp4' }, { type: 'video', file: 'videos/b.mp4' }] }), 'changed');
  const rc = reconcile(sh, { title: 'T', slides: [0, 1, 2, 3].map((n) => slide(n + 1, '')).concat([linkSlide(-6)]) });
  assert.deepEqual([rc.done, rc.sheet.items.length], [1, 0]);
  assert.equal(applySheet(sh, linkSlide()).notes, 'Listen.', '台本には当てない');
});

test('音量: 保存した件を読み戻す・形の違う件は捨てる', () => {
  const sh = setLinkVolume(emptySheet('T'), linkSlide(), 2, -6, 'x');
  assert.deepEqual(readSheet(JSON.stringify(sh), 'T'), sh);
  const x = sh.items[0];
  const bad = [{ ...x, db: '-6' }, { ...x, db: 3 }, { ...x, was: -50 }, { ...x, db: 0 }, { ...x, at: '2' }];
  assert.deepEqual(readSheet(JSON.stringify({ ...sh, items: bad }), 'T').items, []);
});
