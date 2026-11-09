import { test } from 'node:test';
import assert from 'node:assert/strict';
import { integratedLoudness, levelGain, safeGain, dbToAmp, LEVEL_TARGET } from '../../player/js/loudness.js';

const FS = 48000;
const sine = (amp, sec, f = 997, fs = FS) => Float32Array.from({ length: Math.round(sec * fs) }, (_, i) => amp * Math.sin(2 * Math.PI * f * i / fs));

test('1kHz の正弦波（0 dBFS、片方のチャンネルだけ）は -3.01 LUFS（BS.1770 の決まり）', () => {
  assert.ok(Math.abs(integratedLoudness([sine(1, 5)], FS) - -3.01) < 0.1);
  // 標本化の周波数が違っても同じ
  assert.ok(Math.abs(integratedLoudness([sine(1, 5, 997, 44100)], 44100) - -3.01) < 0.1);
});

test('20dB 小さくすれば 20 LU 小さい。左右に同じ音なら 3 LU 大きい', () => {
  assert.ok(Math.abs(integratedLoudness([sine(0.1, 5)], FS) - -23.01) < 0.1);
  const s = sine(0.1, 5);
  assert.ok(Math.abs(integratedLoudness([s, s], FS) - -20.0) < 0.1);
});

test('無音のところは数えない（ゲート）。短すぎる・無音なら -Infinity', () => {
  const tone = sine(0.1, 5);
  const withGap = new Float32Array(tone.length * 3);
  withGap.set(tone, 0);                                 // 5秒鳴って、10秒黙る
  assert.ok(Math.abs(integratedLoudness([withGap], FS) - -23.01) < 0.2);
  assert.equal(integratedLoudness([new Float32Array(FS * 2)], FS), -Infinity);
  assert.equal(integratedLoudness([sine(1, 0.3)], FS), -Infinity);
  assert.equal(integratedLoudness([], FS), -Infinity);
});

test('大きすぎる曲だけ目標まで下げる。見本の曲（-30〜-34 LUFS）と小さい曲はそのまま', () => {
  assert.equal(levelGain(-12), LEVEL_TARGET - -12);       // CD の曲: 18dB 下げる
  assert.equal(levelGain(-25.5), -4.5);
  for (const l of [-29.1, -30.6, -31.7, -33.8, -45]) assert.equal(levelGain(l), 0, String(l));
  assert.equal(levelGain(-28.9), -1.1);
  assert.equal(levelGain(5), -35);
  assert.equal(levelGain(20), -40, '下げるのは 40dB まで');
  assert.equal(levelGain(-Infinity), 0);
  assert.equal(levelGain(NaN), 0);
});

test('受け取った値は掛けてよい範囲に収める（上げない）', () => {
  assert.equal(safeGain(6), 0);
  assert.equal(safeGain(-100), -40);
  assert.equal(safeGain('x'), 0);
  assert.equal(safeGain(undefined), 0);
  assert.equal(safeGain(-18), -18);
  assert.ok(Math.abs(dbToAmp(-20) - 0.1) < 1e-9);
  assert.equal(dbToAmp(3), 1);
});
