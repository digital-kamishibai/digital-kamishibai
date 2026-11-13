// script.md を読んで work.json を作る（docs/work-format.md §2.7）。ビルダー（build_work.py）の読む所を写したもの。
// 2つの読み手は、tests/golden/script/ の同じ答え合わせで縛る——エラーと警告は同じ符号（"slide-numbers"、"cue-unknown line 7"）。
// 文言は英語のまま（ビルダーと同じ）。素材のフォルダは見ない・画面の字は描かない（[Text] は texts に読んで返すだけ）。
// 最初の版は、公開の見本が使う書き方だけを読む。それ以外（[BGM after video]）は "unsupported" で止まる——黙って別の読み方をしない。
// 純粋な関数だけ（node --test で守る）。

import { youtubeId } from './ytlink.js';

export const FORMAT = 'digital-kamishibai/work';
export const VERSION = 1;

const PICTURE_EXTS = ['.jpg', '.jpeg', '.png', '.webp'];
const HEIC_EXTS = ['.heic', '.heif'];
const AUDIO_EXTS = ['.mp3', '.m4a'];
const VIDEO_EXTS = ['.mp4'];
const CUE_KEYWORDS = ['Picture', 'Text', 'BGM', 'BGM once', 'BGM after video', 'BGM stop', 'Sound', 'Video'];
const BGM_KEYWORDS = ['BGM', 'BGM once', 'BGM after video', 'BGM stop'];
// この読み手がまだ読まない合図（見本が使っていない）。ビルダーは読む
const NOT_YET = ['BGM after video'];

const SECONDS = /^(?:(?:([0-9]+):)?([0-9]+):)?([0-9]+(?:\.[0-9]+)?)$/;
const LINK_TIME = /^(?:([0-9]+)h)?(?:([0-9]+)m)?(?:([0-9]+(?:\.[0-9]+)?)s?)?$/;
const LINK = /^https?:\/\//i;
const CAPTIONS = /^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$/;
const VOLUME = /^([+-]?[0-9]+(?:\.[0-9]+)?)dB$/i;
const MIN_VOLUME_DB = -40;

const HEADING = /^## \[Slide ([0-9]+)\][ \t]*(.*?)[ \t]*$/;
const NEAR_HEADING = /^##\s*\[/;
const TITLE = /^# (.+?)[ \t]*$/;
const LANGUAGE = /^>[ \t]*Language:[ \t]*(\S+)[ \t]*$/;
const CUE = /^>[ \t]*\[([^\]]+)\][ \t]*(.*?)[ \t]*$/;
const HOLE_MARK = /^~([0-9]*) /;
const HOLE_NUMBER = /^[1-9][0-9]?$/;
const NEAR_HOLE = /^(?:[～〜][ \t　]|~(?=[^ ~0-9])|~[0-9]+(?![ 0-9]))/;

const TEXT_LENGTH = /^[0-9]+(\.[0-9]{1,2})?in$/;
const TEXT_SIZE = /^[0-9]+pt$/;
const TEXT_COLOR = /^#[0-9A-Fa-f]{6}$/;
const TEXT_CHOICES = { place: ['top', 'middle', 'bottom'], align: ['left', 'center', 'right'], anchor: ['top', 'middle', 'bottom'] };
const TEXT_KEYS = ['place', 'align', 'anchor', 'left', 'top', 'width', 'height', 'size', 'color', 'fill'];
const BOX = ['left', 'top', 'width', 'height'];

function createResult() {
  const r = { errors: [], warnings: [], errorCodes: [], warningCodes: [] };
  r.error = (code, at, text) => { r.errors.push(at ? `${at}: ${text}` : text); r.errorCodes.push(at ? `${code} ${at}` : code); };
  r.warn = (code, at, text) => { r.warnings.push(at ? `${at}: ${text}` : text); r.warningCodes.push(at ? `${code} ${at}` : code); };
  return r;
}

const words = (s) => s.split(/\s+/).filter(Boolean);
const blank = (s) => s.trim() === '';
const extOf = (p) => { const m = /\.[^./]*$/.exec(p); return m ? m[0].toLowerCase() : ''; };

/** 行に分け、制作メモ（<!-- ... -->）を外す。どこにあったかを覚える */
function stripNotes(source, result) {
  const lines = [];
  let inside = false;
  let openedAt = 0;
  source.split('\n').forEach((raw, k) => {
    const number = k + 1;
    const out = [];
    let had = false;
    let pos = 0;
    while (pos <= raw.length) {
      if (inside) {
        const end = raw.indexOf('-->', pos);
        had = true;
        if (end < 0) pos = raw.length + 1;
        else { inside = false; pos = end + 3; }
      } else {
        const start = raw.indexOf('<!--', pos);
        if (start < 0) { out.push(raw.slice(pos)); break; }
        out.push(raw.slice(pos, start));
        inside = true; had = true; openedAt = number;
        pos = start + 4;
      }
    }
    const text = out.join('');
    lines.push({ number, text, hadNote: had, onlyNote: had && blank(text) });
  });
  if (inside) {
    result.error('note-open', `line ${openedAt}`, '"<!--" is never closed with "-->" '
      + '(everything after it would vanish from the narrator\'s screen)');
  }
  return lines;
}

function parseTextAttrs(rest, where, result) {
  const w = words(rest);
  const attrs = {};
  let i = 0;
  while (i < w.length) {
    const key = w[i];
    let value;
    if (key === 'bold') {
      value = true; i += 1;
    } else if (TEXT_KEYS.includes(key)) {
      if (i + 1 >= w.length) { result.error('text-no-value', where, `[Text] "${key}" needs a value`); break; }
      value = w[i + 1]; i += 2;
      const ok = key in TEXT_CHOICES ? TEXT_CHOICES[key].includes(value)
        : BOX.includes(key) ? TEXT_LENGTH.test(value)
          : key === 'size' ? TEXT_SIZE.test(value) : TEXT_COLOR.test(value);
      if (!ok) result.error('text-bad-value', where, `[Text] "${key} ${value}" is not a value it takes`);
    } else {
      result.error('text-unknown-word', where, `[Text] unknown word "${key}" (do not translate the words on a [Text] line)`);
      i += 1;
      continue;
    }
    if (key in attrs) result.error('text-twice', where, `[Text] "${key}" is written twice`);
    attrs[key] = value;
  }
  const lengths = BOX.filter((k) => k in attrs);
  if ('place' in attrs && lengths.length) {
    result.error('text-place-and-box', where, '[Text] write either "place" or left/top/width/height, not both');
  } else if (!('place' in attrs) && lengths.length !== 4) {
    if (lengths.length) {
      const missing = BOX.filter((k) => !(k in attrs)).join(', ');
      result.error('text-box-partial', where, `[Text] needs all four of left/top/width/height (missing: ${missing})`);
    } else {
      result.error('text-no-box', where, '[Text] needs "place top|middle|bottom" or left/top/width/height');
    }
  }
  return attrs;
}

function readSlide(number, title, body, result) {
  const where = `slide ${number}`;
  const notes = [];
  let removed = body.some((l) => l.hadNote);
  const cues = [];
  const pictures = [];
  let bgmCount = 0;
  const texts = [];
  const kept = body.filter((l) => !l.onlyNote);
  let paraMark = null;     // [その段落の印の数字, 行]（§2.3）
  let i = 0;
  while (i < kept.length) {
    const line = kept[i];
    if (!line.text.startsWith('>')) {
      const mark = HOLE_MARK.exec(line.text);
      if (blank(line.text)) paraMark = null;
      if (mark) {
        const digits = mark[1];
        if (digits && !HOLE_NUMBER.test(digits)) {
          result.error('hole-number', `line ${line.number}`, `"~${digits} " is not a hole number `
            + '(write ~1 to ~99 with no leading zero, or "~ " for a hole with no number)');
        } else if (paraMark && paraMark[0] !== digits) {
          result.error('hole-mixed', `line ${line.number}`, `the mark "~${digits} " is not the mark `
            + `"~${paraMark[0]} " of line ${paraMark[1]} in the same paragraph (a paragraph is one hole)`);
        } else if (!paraMark) {
          paraMark = [digits, line.number];
        }
        if (blank(line.text.slice(mark[0].length))) {
          result.warn('hole-empty', `line ${line.number}`, `"~${digits} " (the mark of a hole's narration) with no words after it`);
        }
      } else if (NEAR_HOLE.test(line.text)) {
        result.warn('hole-near', `line ${line.number}`, 'looks like the mark of a hole\'s narration, but the mark is '
          + '"~ " (a half-width tilde and a space). As written, it is read as plain narration');
      }
      notes.push(line.text);
      i += 1;
      continue;
    }
    const block = [line];
    paraMark = null;
    i += 1;
    while (i < kept.length && kept[i].text.startsWith('>')) { block.push(kept[i]); i += 1; }
    const first = CUE.exec(block[0].text);
    if (!first) {                                     // 自由な合図: 語り手の画面に出す
      for (const later of block.slice(1)) {
        const m = CUE.exec(later.text);
        if (m && CUE_KEYWORDS.includes(m[1])) {
          result.error('cue-in-free-cue', `line ${later.number}`, `[${m[1]}] is inside a free cue that starts on `
            + `line ${block[0].number}, so it would do nothing. Put a blank line before it`);
        }
      }
      notes.push(...block.map((b) => b.text));
      continue;
    }
    removed = true;
    if (first[1] === 'Text') {
      const ws = block.slice(1).map((b) => b.text.replace(/^> ?/, ''));
      const attrs = parseTextAttrs(first[2], `line ${block[0].number}`, result);
      for (const b of block.slice(1)) {
        const m = CUE.exec(b.text);
        if (m && CUE_KEYWORDS.includes(m[1])) {
          result.error('cue-in-text-words', `line ${b.number}`, `[${m[1]}] is read as words of the [Text] on line `
            + `${block[0].number}. Put a blank line after the words`);
        }
      }
      if (!ws.some((w) => !blank(w))) {
        result.error('text-no-words', `line ${block[0].number}`, '[Text] has no words (write them on the ">" lines after it)');
      }
      texts.push({ attrs, words: ws });
      continue;
    }
    for (const b of block) {
      const m = CUE.exec(b.text);
      if (!m) {
        result.error('cue-block-mixed', `line ${b.number}`, 'not a machine cue, but inside the cue block that starts on line '
          + `${block[0].number}. Put a blank line between them`);
        continue;
      }
      const [, keyword, arg] = m;
      if (!CUE_KEYWORDS.includes(keyword)) {
        result.error('cue-unknown', `line ${b.number}`, `unknown cue "[${keyword}]" (known: `
          + CUE_KEYWORDS.map((k) => `[${k}]`).join(', ') + '. Do not translate them)');
        continue;
      }
      if (NOT_YET.includes(keyword)) {
        result.error('unsupported', `line ${b.number}`, `[${keyword}] is not read here yet; build the work with the builder`);
        continue;
      }
      if (keyword === 'Text') {
        result.error('text-not-first', `line ${b.number}`, '[Text] must start its own block. Put a blank line before it');
        continue;
      }
      if (keyword === 'BGM stop') {
        if (arg) result.error('bgm-stop-file', `line ${b.number}`, '[BGM stop] takes no file');
      } else if (!arg) {
        result.error('cue-no-file', `line ${b.number}`, `[${keyword}] needs a file path`);
        continue;
      } else if (arg.includes('\\')) {
        result.error('path-backslash', `line ${b.number}`, `use "/" in paths, not "\\": ${arg}`);
      }
      if (keyword === 'Picture') {
        pictures.push(arg);
      } else if (BGM_KEYWORDS.includes(keyword)) {
        bgmCount += 1;
        cues.push(keyword === 'BGM stop' ? { type: 'bgm-stop' }
          : keyword === 'BGM once' ? { type: 'bgm', file: arg, loop: false } : { type: 'bgm', file: arg });
      } else if (keyword === 'Video' && LINK.test(arg)) {
        const cue = linkCue(arg, b.number, result);
        if (cue) cues.push(cue);
      } else {
        cues.push({ type: keyword.toLowerCase(), file: arg });
      }
    }
  }
  if (pictures.length > 1) result.error('picture-twice', where, 'more than one [Picture]');
  if (bgmCount > 1) result.error('bgm-twice', where, 'more than one of [BGM] / [BGM once] / [BGM after video] / [BGM stop]');
  return { number, title, picture: pictures.length ? pictures[0] : null, notes: makeNotes(notes, removed), cues, texts };
}

/** 351 / 351.5 / 5:51 / 1:05:51 → 秒。読めなければ null */
export function seconds(text) {
  const m = SECONDS.exec(text);
  if (!m) return null;
  const [, h, mi] = m;
  const sec = Number(m[3]);
  if ((mi !== undefined && sec >= 60) || (h !== undefined && Number(mi) >= 60)) return null;
  return Number(h || 0) * 3600 + Number(mi || 0) * 60 + sec;
}

function linkSeconds(text) {
  const m = LINK_TIME.exec(text);
  if (!m || !text) return null;
  return Number(m[1] || 0) * 3600 + Number(m[2] || 0) * 60 + Number(m[3] || 0);
}

const plain = (v) => (Number.isInteger(v) ? v : Math.round(v * 1000) / 1000);

function linkCue(arg, line, result) {
  const w = words(arg);
  const url = w[0];
  const rest = w.slice(1);
  const at = `line ${line}`;
  const id = youtubeId(url);
  if (!id) {
    result.error('link-not-youtube', at, `[Video] can play a YouTube link only (got ${url}). `
      + 'For another video, save it as MP4 and write its path');
    return null;
  }
  const said = {};
  if (rest.length % 2) {
    result.error('link-words', at, 'after the link, [Video] takes "start <time>", "end <time>", '
      + `"captions <language>" and "volume <dB>" (got: ${rest.join(' ')})`);
    return null;
  }
  let captions = null;
  let volume = null;
  for (let k = 0; k < rest.length; k += 2) {
    const key = rest[k];
    const value = rest[k + 1];
    if (!['start', 'end', 'captions', 'volume'].includes(key) || key in said
        || (key === 'captions' && captions) || (key === 'volume' && volume !== null)) {
      result.error('link-word', at, 'after the link, [Video] takes "start <time>", "end <time>", '
        + `"captions <language>" and "volume <dB>", once each (got "${key}")`);
      return null;
    }
    if (key === 'volume') {
      const m = VOLUME.exec(value);
      const db = m ? Number(m[1]) : null;
      if (db === null || db > 0 || db < MIN_VOLUME_DB) {
        result.error('link-volume', at, `volume ${value} is not a volume. Write how much quieter, in dB, `
          + `from 0dB to ${MIN_VOLUME_DB}dB, like -6dB (a linked video cannot be made louder)`);
        return null;
      }
      volume = db;
      continue;
    }
    if (key === 'captions') {
      if (!CAPTIONS.test(value)) {
        result.error('link-captions', at, `captions ${value} is not a language (write a code, like ja or en)`);
        return null;
      }
      captions = value;
      continue;
    }
    const sec = seconds(value);
    if (sec === null) {
      result.error('link-time', at, `${key} ${value} is not a time (write seconds, like 351, or m:ss, like 5:51)`);
      return null;
    }
    said[key] = sec;
  }
  // リンクの中の時間（t=・start=・end=）。値の無いもの（?t=）は無いとみなす（Python の parse_qs と同じ）
  let query;
  try { query = new URL(url).searchParams; } catch { query = new URLSearchParams(); }
  const inLink = {};
  for (const [key, names] of [['start', ['start', 't']], ['end', ['end']]]) {
    for (const name of names) {
      const v = query.get(name);
      if (!v) continue;
      const sec = linkSeconds(v);
      if (sec === null) {
        result.error('link-time-in-link', at, `${name}=${v} in the link is not a time`);
        return null;
      }
      inLink[key] = sec;
    }
  }
  const both = Object.keys(said).filter((k) => k in inLink).sort();
  if (both.length) {
    result.error('link-time-twice', at, `[Video] has ${both.join(' and ')} both in the link and after it. `
      + 'Write it once (after the link is easier to read)');
    return null;
  }
  const cut = { ...inLink, ...said };
  if ('end' in cut && cut.end <= (cut.start || 0)) {
    result.error('link-end-before-start', at, '[Video] end must come after start');
    return null;
  }
  const cue = { type: 'video', url: `https://www.youtube.com/watch?v=${id}` };
  if (cut.start) cue.start = plain(cut.start);
  if ('end' in cut) cue.end = plain(cut.end);
  if (captions) cue.captions = captions;
  if (volume) cue.volume = plain(volume);
  return cue;
}

/** §3.2: 太字の印を外す・何か外したときだけ空行の連なりを1つに・両端の空行を落とす */
function makeNotes(lines, removed) {
  let ls = lines.map((l) => l.split('**').join(''));
  if (removed) {
    const folded = [];
    for (const l of ls) {
      if (blank(l) && folded.length && blank(folded[folded.length - 1])) continue;
      folded.push(l);
    }
    ls = folded;
  }
  while (ls.length && blank(ls[0])) ls.shift();
  while (ls.length && blank(ls[ls.length - 1])) ls.pop();
  return ls.join('\n');
}

function guessLanguage(text) {
  if (/[぀-ヿ]/.test(text)) return 'ja';
  if (/[가-힯]/.test(text)) return 'ko';
  if (/[一-鿿]/.test(text)) return 'zh';
  return 'en';
}

/** 素材のフォルダを見ないで分かる所だけ（ビルダーの resolve_media にフォルダを渡さないときと同じ） */
function checkMedia(work, result) {
  for (const slide of work.slides) {
    const where = `slide ${slide.number}`;
    if (slide.picture === null) slide.picture = `pictures/${String(slide.number).padStart(2, '0')}.jpg`;
    const ext = extOf(slide.picture);
    if (HEIC_EXTS.includes(ext)) result.error('picture-heic', where, `${slide.picture} is HEIC, which players cannot show. Export it as JPEG`);
    else if (!PICTURE_EXTS.includes(ext)) result.warn('picture-format', where, `${slide.picture} is not JPEG, PNG or WebP`);
    for (const cue of slide.cues) {
      if (!cue.file) continue;
      const e = extOf(cue.file);
      if (cue.type === 'video' && !VIDEO_EXTS.includes(e)) result.warn('video-format', where, `${cue.file} is not MP4 (H.264 + AAC); listeners will not receive it`);
      if ((cue.type === 'bgm' || cue.type === 'sound') && !AUDIO_EXTS.includes(e)) result.warn('audio-format', where, `${cue.file} is not MP3 or AAC (.m4a)`);
    }
  }
}

/** script.md の文字 → { work（エラーがあれば null）, texts（枚の番号 → [Text] の { attrs, words }）, errors, warnings, errorCodes, warningCodes } */
export function readScript(source) {
  const result = createResult();
  const src = String(source).replace(/^﻿+/, '').replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  const lines = stripNotes(src, result);
  const starts = [];
  lines.forEach((line, index) => {
    if (line.onlyNote) return;
    const m = HEADING.exec(line.text);
    if (m) starts.push([index, Number(m[1]), m[2]]);
    else if (NEAR_HEADING.test(line.text)) {
      result.error('heading-near', `line ${line.number}`, 'looks like a slide heading but is not "## [Slide N] Title" '
        + '(the marker [Slide N] is never translated)');
    }
  });
  const done = (work, texts) => ({
    work: result.errors.length ? null : work, texts, errors: result.errors, warnings: result.warnings,
    errorCodes: result.errorCodes, warningCodes: result.warningCodes,
  });
  if (!starts.length) {
    result.error('no-slides', '', 'no slide headings ("## [Slide 1] Title") were found; nothing to build');
    return done(null, {});
  }
  const header = lines.slice(0, starts[0][0]);
  const titleLine = header.map((l) => TITLE.exec(l.text)).find(Boolean);
  if (!titleLine) result.error('no-title', '', 'the script has no title ("# Title" before the first slide)');
  const langLine = header.map((l) => LANGUAGE.exec(l.text)).find(Boolean);
  const numbers = starts.map((s) => s[1]);
  if (numbers.some((n, k) => n !== k + 1)) {
    result.error('slide-numbers', '', 'slide numbers must be 1, 2, 3, ... with no gaps or repeats; found ' + numbers.join(', '));
  }
  const slides = [];
  starts.forEach(([index, number, slideTitle], k) => {
    const end = k + 1 < starts.length ? starts[k + 1][0] : lines.length;
    let body = lines.slice(index + 1, end);
    const cut = body.findIndex((l) => l.text === '---' && !l.hadNote);
    if (cut >= 0) {
      const after = body.slice(cut + 1).filter((l) => !blank(l.text) && !l.onlyNote);
      if (after.length) result.warn('after-end', `line ${after[0].number}`, `text after "---" of slide ${number} is ignored`);
      body = body.slice(0, cut);
    }
    slides.push(readSlide(number, slideTitle, body, result));
  });
  let language = langLine ? langLine[1] : null;
  if (language === null) {
    language = guessLanguage(slides.map((s) => s.notes).join('\n'));
    result.warn('no-language', '', `no "> Language:" line in the header; guessed "${language}"`);
  }
  const work = { format: FORMAT, version: VERSION, title: titleLine ? titleLine[1] : '', language, slides };
  checkMedia(work, result);
  const texts = {};
  for (const s of slides) {
    if (s.texts.length) texts[s.number] = s.texts;
    delete s.texts;
  }
  return done(work, texts);
}
