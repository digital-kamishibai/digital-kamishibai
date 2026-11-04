import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createPlayback, command, positionAt, vstate, apply, ducking, TOLERANCE } from '../../player/js/playback.js';

test('再生中の位置は、合図のときからの経過を足す', () => {
  let st = command(createPlayback(), 'play', { id: 'v', pos: 10, now: 1000 });
  assert.equal(positionAt(st, 4000), 13);
  st = command(st, 'pause', { pos: 13, now: 4000 });
  assert.equal(positionAt(st, 9000), 13);
  assert.deepEqual(vstate(st, 9000), { t: 'vstate', id: 'v', playing: false, pos: 13 });
  assert.equal(ducking(st), false);
  st = command(st, 'play', { now: 9000 });
  assert.equal(ducking(st), true);
  st = command(st, 'stop', { now: 9500 });
  assert.equal(st.id, null);
  assert.equal(vstate(st, 9500).id, null);
});

test('聞き手: 再生中は1秒以上ずれたときだけ合わせる', () => {
  const msg = { id: 'v', playing: true, pos: 100 };
  assert.deepEqual(apply({ pos: 100.5, paused: false }, msg), { show: true, seek: null, play: null });
  assert.deepEqual(apply({ pos: 100 - TOLERANCE, paused: false }, msg), { show: true, seek: 100, play: null });
  assert.deepEqual(apply({ pos: 0, paused: true }, msg), { show: true, seek: 100, play: true });
});

test('聞き手: 一時停止の合図では、止めて同じ位置に揃える', () => {
  const msg = { id: 'v', playing: false, pos: 42 };
  assert.deepEqual(apply({ pos: 42.3, paused: false }, msg), { show: true, seek: 42, play: false });
  assert.deepEqual(apply({ pos: 42, paused: true }, msg), { show: true, seek: null, play: null });
});

test('聞き手: 動画の無い合図（止めた）では動画を出さない', () => {
  assert.equal(apply({ pos: 3, paused: false }, { id: null, playing: false, pos: 0 }).show, false);
});
