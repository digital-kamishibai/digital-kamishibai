// 音の点呼（段階3 V8・V9）の確かめの音を鳴らす・マイクで測る（語り手・聞き手で共用）。判定は voice.js。
import { TONE_HZ, TONE_MS, toneLevel } from './voice.js';

/** 確かめの音を1回鳴らす（約0.3秒・小さめ。耳ざわりにならないよう、出だしと終わりをなだらかにする） */
export function beep(ctx, gain = 0.25) {
  const osc = ctx.createOscillator();
  const g = ctx.createGain();
  osc.frequency.value = TONE_HZ;
  const t = ctx.currentTime;
  g.gain.setValueAtTime(0, t);
  g.gain.linearRampToValueAtTime(gain, t + 0.03);
  g.gain.setValueAtTime(gain, t + TONE_MS / 1000 - 0.05);
  g.gain.linearRampToValueAtTime(0, t + TONE_MS / 1000);
  osc.connect(g).connect(ctx.destination);
  osc.start(t);
  osc.stop(t + TONE_MS / 1000 + 0.02);
}

/** マイクの流れを ms のあいだ測り、確かめの音の高さがまわりより何 dB 大きかったかの最大を返す。マイクが無ければ null */
export function measure(ctx, stream, ms) {
  if (!stream || !stream.getAudioTracks().some((tr) => tr.readyState === 'live')) return Promise.resolve(null);
  const src = ctx.createMediaStreamSource(stream);
  const an = ctx.createAnalyser();
  an.fftSize = 2048;
  an.smoothingTimeConstant = 0;
  src.connect(an);
  const buf = new Float32Array(an.frequencyBinCount);
  let best = 0;
  return new Promise((resolve) => {
    const timer = setInterval(() => {
      an.getFloatFrequencyData(buf);
      best = Math.max(best, toneLevel(buf, ctx.sampleRate, an.fftSize));
    }, 40);
    setTimeout(() => { clearInterval(timer); src.disconnect(); resolve(best); }, ms);
  });
}
