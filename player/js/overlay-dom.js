// 画面の文字の枠を DOM にする（work-format §3.2 の Drawing）。語り手の画面の下書きと、ビルダーの焼き込み
// （skills/digital-kamishibai/scripts/burn.html）が同じこの関数で描く——描き手が1つなら、下書きと聞き手の絵はずれない。
// 置き場所の計算は layout.js の drawBox。CSS は app.css の `.lay .b`（同じものを両方が読む）。
import { drawBox } from './layout.js';

/** 枠1つ → div.b（段落ごとに p）。scale＝画面の px / EMU。words＝段落の並び（段落ごとに行の並び） */
export function boxElement(doc, box, words, scale) {
  const d = drawBox(box, words, scale);
  const el = doc.createElement('div');
  el.className = 'b';
  Object.assign(el.style, d.box);
  // ⚠️ 段落の間に空白・改行の文字を置かない（pre-wrap で空の1行になる。段階0の2）
  for (const p of d.paragraphs) {
    const pe = doc.createElement('p');
    Object.assign(pe.style, p.css);
    pe.textContent = p.lines.join('\n');
    el.append(pe);
  }
  return el;
}
