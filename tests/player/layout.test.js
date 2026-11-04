import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  EMU_PER_IN, STEP, snapGrid, toIn, fromIn, editOf, applyEdit, snapCenter, moveBy, resizeBy, nudge, resize,
  sheetValues, diffLayout, layoutLines, judgeLayout, applyLayoutItem, isLayoutValues, drawBox,
  boxColor, luma, meanLuma, contrast, CONTRAST_MIN, workPalette,
} from '../../player/js/layout.js';
import { setSlideEdits, emptySheet, judge, applySheet, sheetMarkdown, readSheet, reconcile } from '../../player/js/corrections.js';

const SLIDE = { width: 12192000, height: 6858000 };
const para = (o = {}) => ({ align: 'center', space_before: 0, size: 30, bold: true, color: '#2A2A3A', font: 'Meiryo', ...o });
// 実際の作品の表紙の見出しと同じ値（top_bar・top=0.55in・height=1.1in・54pt）
const head = () => ({ x: 457200, y: 502920, width: 11247120, height: 1005840, inset: [91440, 45720, 91440, 45720], anchor: 'top', wrap: true, paragraphs: [para({ size: 54 })] });
const sub = () => ({ x: 457200, y: 1463040, width: 11247120, height: 640080, inset: [91440, 45720, 91440, 45720], anchor: 'top', wrap: true, paragraphs: [para()] });
const slide1 = () => ({ number: 1, title: '', picture: 'pictures/01.jpg', notes: 'はじめ', cues: [],
  overlays: [[['だれも、悪くないのに']], [['〜協力の科学〜']]], overlay_layout: [head(), sub()], overlay_base: 'overlay_base/01.jpg' });

test('0.01インチの格子・インチと EMU', () => {
  assert.equal(STEP, 9144);
  assert.equal(snapGrid(164592 + 4000), 164592);   // 0.18in の近く → 0.18in
  assert.equal(toIn(502920), 0.55);
  assert.equal(fromIn(0.55), 502920);
});

test('直せる値は位置・大きさ・文字の大きさ。大きさは全段落に効く', () => {
  const b = { ...head(), paragraphs: [para(), para({ space_before: 14 })] };
  assert.deepEqual(editOf(b), { x: 457200, y: 502920, width: 11247120, height: 1005840, size: 30, color: '#2A2A3A', fill: null });
  const a = applyEdit(b, { ...editOf(b), y: 600000, size: 32 });
  assert.equal(a.y, 600000);
  assert.deepEqual(a.paragraphs.map((p) => p.size), [32, 32]);
  assert.equal(a.paragraphs[1].space_before, 14);  // ほかの書式は変えない
});

test('ドラッグ: 0.01インチの格子へ・中心がスライドの中心に近ければ吸い付く', () => {
  const e = editOf(head());                         // 横はもともと中央（0.5in + 12.3in = 12.8in の中心＝6.67in ≒ 13.333/2）
  const r = moveBy(e, 3000, 20000, SLIDE, 20000);
  assert.equal(r.guides.v, true);
  assert.equal(r.edit.x, SLIDE.width / 2 - e.width / 2);
  assert.equal(r.edit.y % STEP, 0);
  assert.equal(r.guides.h, false);
  const far = moveBy(e, 300000, 0, SLIDE, 20000);
  assert.equal(far.guides.v, false);
  assert.equal(far.edit.x % STEP, 0);
  assert.deepEqual(snapCenter(100, 50, 300, 10), { pos: 100, snapped: false });
  assert.deepEqual(snapCenter(120, 50, 300, 10), { pos: 125, snapped: true });
});

test('つまみ: つかんだ角が動き、向かいの角は動かない。0.1インチより小さくしない', () => {
  const e = { x: fromIn(1), y: fromIn(1), width: fromIn(4), height: fromIn(2), size: 30 };
  const se = resizeBy(e, 'se', fromIn(0.5), fromIn(-0.25));
  assert.deepEqual([toIn(se.x), toIn(se.y), toIn(se.width), toIn(se.height)], [1, 1, 4.5, 1.75]);
  const nw = resizeBy(e, 'nw', fromIn(0.5), fromIn(0.5));
  assert.deepEqual([toIn(nw.x), toIn(nw.y), toIn(nw.x + nw.width), toIn(nw.y + nw.height)], [1.5, 1.5, 5, 3]);
  const tiny = resizeBy(e, 'ne', fromIn(-10), fromIn(10));
  assert.equal(tiny.width, EMU_PER_IN / 10);
  assert.equal(toIn(tiny.y + tiny.height), 3);
});

test('矢印キーは 0.01インチ（Shift で 0.1インチ）・文字の大きさは 1pt 刻み', () => {
  const e = { x: 0, y: 0, width: 1, height: 1, size: 30 };
  assert.deepEqual([nudge(e, 'ArrowRight', false).x, nudge(e, 'ArrowUp', true).y], [9144, -91440]);
  assert.equal(nudge(e, 'Enter', false), e);
  assert.equal(resize(e, 2).size, 32);
  assert.equal(resize({ ...e, size: 1 }, -5).size, 1);
});

test('修正票の件: 変わった値だけ・インチ小数2桁・整数 pt。変わっていなければ件にしない', () => {
  const b = head();
  assert.equal(diffLayout(1, 1, b, { ...editOf(b), x: b.x + 1000 }), null);   // 丸めると同じ
  const item = diffLayout(1, 1, b, { ...editOf(b), y: fromIn(0.7), size: 56 });
  assert.deepEqual(item, { slide: 1, kind: 'layout', at: 1, before: { top: 0.55, size: 54 }, after: { top: 0.7, size: 56 } });
  assert.equal(layoutLines(item.before), 'top 0.55in\nsize 54pt');
  assert.equal(layoutLines({ size: 32, left: 0.5 }), 'left 0.50in\nsize 32pt');   // 並びは left・top・width・height・size
  assert.deepEqual(sheetValues(editOf(b)), { left: 0.5, top: 0.55, width: 12.3, height: 1.1, size: 54, color: '#2A2A3A', fill: 'none' });
});

test('反映の判定: 全部 After→反映済み／全部 Before→未反映／それ以外→手を入れて反映', () => {
  const item = { slide: 1, kind: 'layout', at: 1, before: { top: 0.55, size: 54 }, after: { top: 0.7, size: 56 } };
  const with_ = (y, size) => ({ ...slide1(), overlay_layout: [{ ...head(), y: fromIn(y), paragraphs: [para({ size })] }, sub()] });
  assert.equal(judgeLayout(item, with_(0.7, 56)), 'done');
  assert.equal(judgeLayout(item, with_(0.55, 54)), 'pending');
  assert.equal(judgeLayout(item, with_(0.72, 56)), 'reworded');
  assert.equal(judgeLayout({ ...item, at: 5 }, slide1()), 'reworded');            // 枠が無くなった
  assert.equal(judge(item, with_(0.7, 56)), 'done');                               // 修正票の judge からも同じ
});

test('当てる: 元の値のままの枠にだけ当てる', () => {
  const item = { slide: 1, kind: 'layout', at: 1, before: { top: 0.55 }, after: { top: 0.7 } };
  assert.deepEqual(applyLayoutItem(item, head()), { ...editOf(head()), y: fromIn(0.7) });
  assert.equal(applyLayoutItem(item, { ...head(), y: fromIn(0.6) }), null);
  assert.ok(isLayoutValues({ top: 0.7 }) && !isLayoutValues({}) && !isLayoutValues({ top: '0.7' }) && !isLayoutValues({ color: 1 }));
});

test('修正票: 枚を閉じると layout の件ができ、当てる・Markdown・保存・読み直しが通る', () => {
  const s = slide1();
  let sheet = setSlideEdits(emptySheet('t'), s, {
    notes: s.notes, overlays: s.overlays,
    layout: [{ ...editOf(head()), y: fromIn(0.7), size: 56 }, editOf(sub())],      // 2枠目は動かしていない
  });
  assert.equal(sheet.items.length, 1);
  assert.deepEqual(sheet.items[0], { slide: 1, kind: 'layout', at: 1, before: { top: 0.55, size: 54 }, after: { top: 0.7, size: 56 } });
  const ap = applySheet(sheet, s);
  assert.deepEqual([...ap.edited.layout], [1]);
  assert.equal(ap.layout[0].y, fromIn(0.7));
  assert.equal(ap.layout[1], null);
  const md = sheetMarkdown(sheet, new Date(2026, 9, 25, 21, 4));
  assert.match(md, /## \[Slide 1\] layout 1\n### Before\n```\ntop 0\.55in\nsize 54pt\n```\n### After\n```\ntop 0\.70in\nsize 56pt\n```/);
  assert.deepEqual(readSheet(JSON.stringify(sheet), 't'), sheet);                  // ブラウザの中への保存で消えない
  // 文も直した枚: notes → overlay → layout の順
  sheet = setSlideEdits(sheet, s, { notes: 'はじめに', overlays: [[['だれも']], s.overlays[1]], layout: [{ ...editOf(head()), y: fromIn(0.7), size: 56 }, null] });
  assert.deepEqual(sheet.items.map((x) => x.kind), ['notes', 'overlay', 'layout']);
  // 読み直し: 書き戻されて再ビルドされたら、自動で消える
  const rebuilt = { ...s, overlay_layout: [{ ...head(), y: fromIn(0.7), paragraphs: [para({ size: 56 })] }, sub()] };
  const rc = reconcile(sheet, { slides: [rebuilt] });
  assert.deepEqual(rc.sheet.items.map((x) => x.kind), ['notes', 'overlay']);
});

// ---------- 文字色と下地の色（work-format §3.2 の The colour of a box・§6 の color・fill） ----------

test('枠の色は文字のある段落から。空の段落の色は数えない・文字のある段落で割れたら null', () => {
  const b = { ...head(), paragraphs: [para({ color: '#7a4518' }), para({ color: '#000000' }), para({ color: '#7A4518' })] };
  assert.equal(boxColor(b, [['上'], [''], ['下']]), '#7A4518');                     // 空の段落はテーマの黒に落ちていても数えない
  assert.equal(boxColor(b, [['上'], [' '], ['下']]), '#7A4518');                    // 空白だけの段落も空
  assert.equal(boxColor(b, [['上'], ['中'], ['下']]), null);                         // 文字のある段落で割れた
  assert.equal(boxColor(b), null);                                                  // 文字が分からなければ全段落を見る
  assert.equal(boxColor({ ...b, paragraphs: [para({ color: '#000000' })] }, [['']]), '#000000');  // 全部空なら全段落
  assert.equal(editOf(b, [['上'], [''], ['下']]).color, '#7A4518');
  assert.equal(editOf({ ...head(), fill: '#faf7f0' }).fill, '#FAF7F0');               // 大文字にそろえる
});

test('色を当てる: 文字色は全段落に・下地は null で消える（文字列 none は残さない）', () => {
  const b = { ...head(), fill: '#FFFFFF', paragraphs: [para(), para({ space_before: 14 })] };
  const a = applyEdit(b, { ...editOf(b), color: '#FFFFFF', fill: null });
  assert.deepEqual(a.paragraphs.map((p) => p.color), ['#FFFFFF', '#FFFFFF']);
  assert.equal('fill' in a, false);
  assert.equal(applyEdit(head(), { ...editOf(head()), fill: '#1E2C4A' }).fill, '#1E2C4A');
  const mixed = { ...head(), paragraphs: [para({ color: '#111111' }), para({ color: '#222222' })] };
  assert.deepEqual(applyEdit(mixed, editOf(mixed)).paragraphs.map((p) => p.color), ['#111111', '#222222']);  // 色の無い枠は段落の色のまま
  assert.equal(applyEdit(b, { x: 1, y: 1, width: 1, height: 1, size: 30 }).fill, '#FFFFFF');  // 色を持たない値は下地に触らない
});

test('修正票の件: 色は大文字・下地なしは fill none・並びは size の後に color・fill', () => {
  const b = head();
  const item = diffLayout(1, 1, b, { ...editOf(b), color: '#ffffff', fill: '#1e2c4a' });
  assert.deepEqual(item, { slide: 1, kind: 'layout', at: 1,
    before: { color: '#2A2A3A', fill: 'none' }, after: { color: '#FFFFFF', fill: '#1E2C4A' } });
  assert.equal(layoutLines({ fill: 'none', color: '#FFFFFF', size: 32, top: 0.3 }), 'top 0.30in\nsize 32pt\ncolor #FFFFFF\nfill none');
  // 下地を消した
  assert.deepEqual(diffLayout(1, 1, { ...b, fill: '#FFFFFF' }, { ...editOf(b), fill: null }).after, { fill: 'none' });
  // 色の無い枠（段落で割れている）には color の行を作らない
  const mixed = { ...b, paragraphs: [para({ color: '#111111' }), para({ color: '#222222' })] };
  assert.equal(diffLayout(1, 1, mixed, editOf(mixed), [['a'], ['b']]), null);
  // 色を持たない値（色の欄の無いころの直し）は、色の差分にしない
  assert.deepEqual(diffLayout(1, 1, b, { x: b.x, y: fromIn(0.7), width: b.width, height: b.height, size: 54 }).after, { top: 0.7 });
});

test('色の反映の判定と当てる: fill none と「fill が無い」は同じ・大文字小文字は問わない', () => {
  const item = { slide: 1, kind: 'layout', at: 1, before: { color: '#2A2A3A', fill: 'none' }, after: { color: '#FFFFFF', fill: '#1E2C4A' } };
  const with_ = (color, fill) => ({ ...slide1(), overlay_layout: [{ ...head(), ...(fill ? { fill } : {}), paragraphs: [para({ size: 54, color })] }, sub()] });
  assert.equal(judgeLayout(item, with_('#ffffff', '#1e2c4a')), 'done');
  assert.equal(judgeLayout(item, with_('#2A2A3A')), 'pending');
  assert.equal(judgeLayout(item, with_('#FFFFFF')), 'reworded');                      // 文字色だけ入った
  const off = { slide: 1, kind: 'layout', at: 1, before: { fill: '#FFFFFF' }, after: { fill: 'none' } };
  assert.equal(judgeLayout(off, with_('#2A2A3A')), 'done');                           // 下地が無い＝fill none
  assert.equal(judgeLayout(off, with_('#2A2A3A', '#FFFFFF')), 'pending');
  // いまは色が段落で割れている枠: color の件は「手を入れて反映」
  const split = { ...slide1(), overlays: [[['a'], ['b']], [['〜協力の科学〜']]],
    overlay_layout: [{ ...head(), paragraphs: [para({ color: '#FFFFFF' }), para({ color: '#000000' })] }, sub()] };
  assert.equal(judgeLayout(item, split), 'reworded');
  // 当てる
  const e = applyLayoutItem(item, head(), [['だれも、悪くないのに']]);
  assert.deepEqual([e.color, e.fill], ['#FFFFFF', '#1E2C4A']);
  assert.equal(applyLayoutItem(off, { ...head(), fill: '#FFFFFF' }).fill, null);
  assert.equal(applyLayoutItem(off, head()), null);                                     // もう下地が無い＝元の値ではない
  assert.equal(applyLayoutItem({ ...item, before: { color: '#000000' }, after: { color: '#FFFFFF' } }, head()), null);
});

test('保存した票の色の件は読み直しで消えない（値の種類ごとの型の検査）', () => {
  assert.ok(isLayoutValues({ color: '#FFFFFF', fill: 'none' }));
  assert.ok(isLayoutValues({ top: 0.3, fill: '#1E2C4A' }));
  assert.ok(!isLayoutValues({ color: 'none' }) && !isLayoutValues({ color: 'white' }) && !isLayoutValues({ fill: '#fff' }));
  assert.ok(!isLayoutValues({ size: '#FFFFFF' }) && !isLayoutValues({ bold: true }));
  const s = slide1();
  const sheet = setSlideEdits(emptySheet('t'), s, {
    notes: s.notes, overlays: s.overlays, layout: [{ ...editOf(head()), color: '#FFFFFF', fill: '#1E2C4A' }, editOf(sub())],
  });
  assert.deepEqual(sheet.items[0].after, { color: '#FFFFFF', fill: '#1E2C4A' });
  assert.deepEqual(readSheet(JSON.stringify(sheet), 't'), sheet);
  const md = sheetMarkdown(sheet, new Date(2026, 9, 30, 10, 0));
  assert.match(md, /## \[Slide 1\] layout 1\n### Before\n```\ncolor #2A2A3A\nfill none\n```\n### After\n```\ncolor #FFFFFF\nfill #1E2C4A\n```/);
  const ap = applySheet(sheet, s);
  assert.deepEqual([ap.layout[0].color, ap.layout[0].fill], ['#FFFFFF', '#1E2C4A']);
  // 書き戻されて再ビルドされたら消える
  const rebuilt = { ...s, overlay_layout: [{ ...head(), fill: '#1E2C4A', paragraphs: [para({ size: 54, color: '#FFFFFF' })] }, sub()] };
  assert.equal(reconcile(sheet, { slides: [rebuilt] }).sheet.items.length, 0);
});

test('色見本: その作品の文字色と下地の色をよく使う順に・白と黒は最後に1つずつ', () => {
  const s1 = slide1();                                                             // 2枠とも #2A2A3A
  const s2 = { ...slide1(), number: 2, overlays: [[['a'], ['']], [['b']]],
    overlay_layout: [{ ...head(), fill: '#faf7f0', paragraphs: [para({ color: '#7A4518' }), para({ color: '#000000' })] },
      { ...sub(), fill: '#FFFFFF', paragraphs: [para({ color: '#7A4518' })] }] };
  assert.deepEqual(workPalette({ slides: [s1, s2] }), ['#2A2A3A', '#7A4518', '#FAF7F0', '#FFFFFF', '#000000']);  // 空の段落の黒は数えない
  assert.deepEqual(workPalette({ slides: [] }), ['#FFFFFF', '#000000']);
  assert.equal(workPalette({ slides: [s1, s2] }, 3).length, 3);
});

test('明暗差の目安: 明るさ 0.299R+0.587G+0.114B・下地があれば下地の色・70 未満で印', () => {
  assert.equal(CONTRAST_MIN, 70);
  assert.equal(luma('#FFFFFF'), 255);
  assert.equal(luma('#000000'), 0);
  assert.ok(Math.abs(luma('#7A4518') - (0.299 * 122 + 0.587 * 69 + 0.114 * 24)) < 1e-9);
  assert.equal(meanLuma(new Uint8ClampedArray([255, 255, 255, 255, 0, 0, 0, 255])), 127.5);
  assert.ok(Number.isNaN(meanLuma(new Uint8ClampedArray([]))));
  const e = { ...editOf(head()), color: '#FFFFFF', fill: null };
  assert.deepEqual(contrast(e, 200), { gap: 55, low: true });
  assert.deepEqual(contrast(e, 100), { gap: 155, low: false });
  assert.equal(contrast({ ...e, fill: '#FFFFFF' }, 0).low, true);                  // 下地があれば絵の明るさは見ない
  assert.equal(contrast({ ...e, color: null }, 100), null);                         // 色の無い枠
  assert.equal(contrast(e, NaN), null);                                             // 背景が測れない
});

test('描き方: 1920px 幅で、1pt＝2px・段落の前の空き・空の段落も1行・角丸の中の余白・回転', () => {
  const scale = 1920 / SLIDE.width;
  const d = drawBox({ ...head(), paragraphs: [para({ size: 54 }), para({ size: 20 }), para({ space_before: 14 })] }, [['見出し'], [''], ['下']], scale);
  assert.equal(parseFloat(d.box.left), 72);                                       // 0.5in × 144px
  assert.equal(d.box.justifyContent, 'flex-start');
  assert.deepEqual(d.paragraphs.map((p) => p.css.fontSize), ['108px', '40px', '60px']);
  assert.equal(d.paragraphs[0].css.marginTop, undefined);
  assert.equal(d.paragraphs[2].css.marginTop, '28px');
  assert.deepEqual(d.paragraphs[1].lines, ['​']);
  assert.equal(d.paragraphs[0].css.whiteSpace, 'pre-wrap');
  const rr = drawBox({ ...head(), shape: 'roundRect', corner: 0.25, fill: '#F7EED6', outline: { color: '#C9A84A', width: 19050 }, rotation: 3.5, anchor: 'middle', wrap: false },
    [['a'], ['足した段落']], scale);
  const corner = 0.25 * 1005840 * 0.29289;
  assert.equal(rr.box.padding.split(' ')[0], `${(45720 + corner) * scale}px`);
  assert.equal(rr.box.justifyContent, 'center');
  assert.equal(rr.box.transform, 'rotate(3.5deg)');
  assert.equal(rr.box.background, '#F7EED6');
  assert.equal(rr.paragraphs[0].css.whiteSpace, 'pre');
  assert.equal(rr.paragraphs[1].css.fontSize, '108px');                            // 足した段落は最後の段落の書式
});
