// 端末で BGM・効果音を鳴らす（語り手・聞き手で共用）。設計: プラン「段階4の実装設計」P3・P5・P6・P8。
// 音は <audio> → Web Audio の GainNode を通す——iPhone の Safari は <audio> の音量（volume）を無視するため。
// 曲はファイルを丸ごと解析しない（スマートフォンのメモリ）。<audio> がディスクから少しずつ読む。

import { CROSSFADE_MS, FADE_OUT_MS, DUCK, TALK_DUCK_DB, TALK_DOWN_TC, TALK_UP_TC, bgmPosition } from './audio.js';
import { TOLERANCE } from './playback.js';

export function createEngine() {
  let ctx = null;
  let master = null;          // 全体（動画のあいだの下げ・当日の音量つまみ）
  let out = null;             // この端末のスピーカーへ（「この端末でも鳴らす」の消音）。録画は master から取る
  let deck = null;            // いま鳴っている BGM { id, url, el, gain }
  let ducked = false;
  let talking = false;        // 語り手が話している（そのあいだ BGM を下げる。T2）
  let muted = false;
  let music = 1;             // 当日の音量つまみ（BGM・効果音。0〜2）
  let played = 0;            // 鳴らした効果音の数（自動テスト用）

  function ensure() {
    if (ctx) return;
    const AC = window.AudioContext || window.webkitAudioContext;
    ctx = new AC();
    master = ctx.createGain();
    out = ctx.createGain();
    master.connect(out).connect(ctx.destination);
    applyMaster();
  }

  function applyMaster(tc = 0.25) {
    if (!master) return;
    const v = (ducked ? DUCK : 1) * (talking ? 10 ** (TALK_DUCK_DB / 20) : 1) * music;
    master.gain.cancelScheduledValues(ctx.currentTime);
    master.gain.setTargetAtTime(v, ctx.currentTime, tc);
    out.gain.cancelScheduledValues(ctx.currentTime);
    out.gain.setTargetAtTime(muted ? 0 : 1, ctx.currentTime, 0.25);
  }

  function ramp(gain, to, ms) {
    const t = ctx.currentTime;
    gain.gain.cancelScheduledValues(t);
    gain.gain.setValueAtTime(gain.gain.value, t);
    gain.gain.linearRampToValueAtTime(to, t + ms / 1000);
  }

  function newDeck(id, url, loop) {
    const el = new Audio();
    el.src = url;
    el.loop = loop;
    el.preload = 'auto';
    const src = ctx.createMediaElementSource(el);
    const gain = ctx.createGain();
    gain.gain.value = 0;
    src.connect(gain).connect(master);
    return { id, url, el, gain };
  }

  function retire(d, ms) {
    ramp(d.gain, 0, ms);
    setTimeout(() => { d.el.pause(); d.el.removeAttribute('src'); d.el.load(); }, ms + 100);
  }

  function seekAndPlay(d, msg) {
    const go = () => {
      const pos = bgmPosition(msg, d.el.duration);
      if (pos == null) { d.el.pause(); return; } // 1回きりの曲は、もう終わっている
      if (Math.abs(d.el.currentTime - pos) >= TOLERANCE) d.el.currentTime = pos;
      if (msg.playing && d.el.paused) d.el.play().catch(() => {});
      if (!msg.playing && !d.el.paused) d.el.pause();
    };
    if (d.el.readyState >= 1) go(); else d.el.addEventListener('loadedmetadata', go, { once: true });
  }

  return {
    /** 画面に触れた操作の中で呼ぶ（ブラウザは触れる前の音を止める）。戻り値: 音を出せるようになったか */
    async unlock() {
      ensure();
      try { if (ctx.state !== 'running') await ctx.resume(); } catch { /* 触れていない */ }
      return ctx.state === 'running';
    },
    get unlocked() { return !!ctx && ctx.state === 'running'; },

    /** BGM の合図を反映する。urlOf(id) → 保存した素材の URL（まだ無ければ null） */
    setBgm(msg, urlOf) {
      ensure();
      const url = msg && msg.id ? urlOf(msg.id) : null;
      if (!url) {
        if (deck) { retire(deck, FADE_OUT_MS); deck = null; }
        return;
      }
      if (deck && deck.id === msg.id) { seekAndPlay(deck, msg); return; }
      const old = deck;
      deck = newDeck(msg.id, url, msg.loop);
      seekAndPlay(deck, msg);
      ramp(deck.gain, 1, old ? CROSSFADE_MS : 300);
      if (old) retire(old, CROSSFADE_MS);
    },

    playSound(url) {
      if (!url) return;
      ensure();
      const el = new Audio(url);
      played += 1;
      ctx.createMediaElementSource(el).connect(master);
      el.addEventListener('ended', () => el.removeAttribute('src'), { once: true });
      el.play().catch(() => {});
    },

    duck(on) { ducked = !!on; applyMaster(); },
    /** 語り手が話している／いない（T2）。下げるのは速く・戻すのはゆっくり */
    talk(on) { if (talking === !!on) return; talking = !!on; applyMaster(talking ? TALK_DOWN_TC : TALK_UP_TC); },
    mute(on) { muted = !!on; applyMaster(); },
    setMusic(v) { music = Math.min(2, Math.max(0, Number(v) || 0)); applyMaster(); },

    /** 録画用の取り出し口（録画と練習 G1）。聞き手の端末で鳴っているのと同じ音（動画のあいだの下げ・音量つまみを含む）。
     *  「この端末でも鳴らす」を切っていても録画には入る（消音の手前から取る） */
    tap() {
      ensure();
      const d = ctx.createMediaStreamDestination();
      master.connect(d);
      return { stream: d.stream, close: () => { try { master.disconnect(d); } catch { /* 外し済み */ } } };
    },

    /** 自動テスト用: いま鳴らしている BGM */
    state() {
      return { bgm: deck ? deck.id : null, playing: !!deck && !deck.el.paused, pos: deck ? deck.el.currentTime : 0, ducked, talking, muted, music, played, ctx: ctx ? ctx.state : 'none' };
    },
  };
}
