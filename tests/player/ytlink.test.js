import { test } from 'node:test';
import assert from 'node:assert/strict';
import { youtubeId, isLink, cutOf, clampCut, atEnd, jumped, embedSrc, errorReason, isCaptions, EMBED_ORIGIN, END_EARLY } from '../../player/js/ytlink.js';

test('YouTube のリンクの形をどれも読む', () => {
  for (const url of [
    'https://www.youtube.com/watch?v=8KkKuTCFvzI',
    'https://www.youtube.com/watch?v=8KkKuTCFvzI&t=351s',
    'https://youtube.com/watch?feature=share&v=8KkKuTCFvzI',
    'https://m.youtube.com/watch?v=8KkKuTCFvzI',
    'https://youtu.be/8KkKuTCFvzI?t=351',
    'https://www.youtube.com/embed/8KkKuTCFvzI?start=351&end=369',
    'https://www.youtube-nocookie.com/embed/8KkKuTCFvzI',
    'https://www.youtube.com/shorts/8KkKuTCFvzI',
    'https://www.youtube.com/live/8KkKuTCFvzI',
  ]) assert.equal(youtubeId(url), '8KkKuTCFvzI', url);
});

test('YouTube でないリンク・ID の形でないものは読まない', () => {
  for (const url of [
    'videos/clip.mp4', '', null, 'https://vimeo.com/12345678', 'https://www.youtube.com.evil.example/watch?v=8KkKuTCFvzI',
    'https://www.youtube.com/watch?v=short', 'https://www.youtube.com/watch?v=8KkKuTCFvzI"x', 'javascript:alert(1)',
    'https://www.youtube.com/channel/UCAuUUnT6oDeKwE6v1NGQxug', 'ftp://youtu.be/8KkKuTCFvzI',
  ]) assert.equal(youtubeId(url), null, String(url));
});

test('リンクの合図かどうか', () => {
  assert.equal(isLink({ type: 'video', url: 'https://youtu.be/8KkKuTCFvzI' }), true);
  assert.equal(isLink({ type: 'video', file: 'videos/a.mp4' }), false);
  assert.equal(isLink({ type: 'sound', url: 'x' }), false);
});

test('流す範囲: 止める秒が無ければ終わりまで。範囲の外の頭出しは範囲に収める', () => {
  assert.deepEqual(cutOf({ start: 351, end: 369 }), { start: 351, end: 369 });
  assert.deepEqual(cutOf({ start: 45 }), { start: 45, end: Infinity });
  assert.deepEqual(cutOf({ end: null }), { start: 0, end: Infinity });
  const cut = cutOf({ start: 351, end: 369 });
  assert.equal(clampCut(10, cut), 351);
  assert.equal(clampCut(400, cut), 369);
  assert.equal(clampCut(360, cut), 360);
});

test('止める秒の少し手前で止める（間をおいて見るので、行き過ぎて関連動画が出ないように）', () => {
  const cut = { start: 351, end: 369 };
  assert.equal(atEnd(369 - END_EARLY - 0.01, cut), false);
  assert.equal(atEnd(369 - END_EARLY, cut), true);
  assert.equal(atEnd(1e6, { start: 0, end: Infinity }), false);
});

test('頭出しを位置の飛びで見つける（流しているあいだは経過を差し引く）', () => {
  // 流している: 1秒たって1秒進んだ＝頭出しではない。1秒たって 30秒進んだ・戻った＝頭出し
  assert.equal(jumped({ t: 10, at: 0, playing: true }, { t: 11.05, at: 1000, playing: true }), false);
  assert.equal(jumped({ t: 10, at: 0, playing: true }, { t: 40, at: 1000, playing: true }), true);
  assert.equal(jumped({ t: 10, at: 0, playing: true }, { t: 5, at: 1000, playing: true }), true);
  // 止めている: 少しでも動けば頭出し
  assert.equal(jumped({ t: 10, at: 0, playing: false }, { t: 10, at: 1000, playing: false }), false);
  assert.equal(jumped({ t: 10, at: 0, playing: false }, { t: 12, at: 1000, playing: false }), true);
  // 流し始めた・止めた瞬間は頭出しとみなさない（'play'・'pause' が別に来る）
  assert.equal(jumped({ t: 10, at: 0, playing: false }, { t: 30, at: 1000, playing: true }), false);
  assert.equal(jumped(null, { t: 30, at: 1000, playing: true }), false);
});

test('埋め込みの URL: クッキーを置かない埋め込み・関連動画を絞る・止める秒は渡さない', () => {
  const u = new URL(embedSrc('8KkKuTCFvzI', { start: 351.5, controls: false, origin: 'https://digitalkamishibai.org' }));
  assert.equal(u.origin, EMBED_ORIGIN);
  assert.equal(u.pathname, '/embed/8KkKuTCFvzI');
  const q = Object.fromEntries(u.searchParams);
  assert.equal(q.enablejsapi, '1');
  assert.equal(q.rel, '0');
  assert.equal(q.controls, '0');
  assert.equal(q.disablekb, '1');
  assert.equal(q.start, '351');
  assert.equal(q.origin, 'https://digitalkamishibai.org');
  assert.equal(q.end, undefined);
  assert.equal(q.cc_load_policy, undefined, '字幕は指定したときだけ');
  const narrator = Object.fromEntries(new URL(embedSrc('8KkKuTCFvzI')).searchParams);
  assert.equal(narrator.controls, '1');
  assert.equal(narrator.start, undefined);
});

test('字幕: 言語を指定すると、最初から出す。言語の形でなければ何もしない', () => {
  const q = Object.fromEntries(new URL(embedSrc('8KkKuTCFvzI', { captions: 'ja' })).searchParams);
  assert.equal(q.cc_load_policy, '1');
  assert.equal(q.cc_lang_pref, 'ja');
  const bad = Object.fromEntries(new URL(embedSrc('8KkKuTCFvzI', { captions: 'ja&autoplay=1' })).searchParams);
  assert.equal(bad.cc_load_policy, undefined);
  assert.equal(bad.autoplay, undefined);
  assert.ok(isCaptions('pt-BR') && isCaptions('en') && !isCaptions('') && !isCaptions('日本語') && !isCaptions(null));
});

test('流せない理由の番号を言葉にする', () => {
  assert.equal(errorReason(150), 'blocked');
  assert.equal(errorReason(101), 'blocked');
  assert.equal(errorReason(100), 'gone');
  assert.equal(errorReason(2), 'bad-link');
  assert.equal(errorReason(153), 'referrer');
  assert.equal(errorReason(5), 'player');
});
