// 語り手の PC で声を混ぜる（段階3 V1）。聞き手ごとに「語り手の声＋その聞き手以外の聞き手の声」の出口を作る。
// 誰の声を届けるか（heard）は voice.js が決め、ここはそのとおりに音量の栓を開け閉めするだけ。
// 配線は固定（全員の入口 → 自分以外の全員の出口）で、栓（GainNode）だけを動かす——つなぎ直しで音が途切れないように。
//
// ⚠️ Chrome は、WebRTC で受けた流れを Web Audio にだけつなぐと無音になることがある。
//    受けた流れを、音を消した <audio> にもつないでおく（下の keepAlive）。

const GATE_DB = -50;       // これより小さい音は届けない（小さい音の門。BGM・部屋の雑音の回り込みを減らす。V7）
const GATE_HOLD_MS = 400;  // 声が途切れても、この時間は門を開けておく（語尾が切れないように）
const SPEAK_DB = -45;      // 札の「話している」の印

export function createMixer(ctx) {
  const narrator = { src: null, gain: ctx.createGain(), stream: null };
  narrator.gain.gain.value = 1;
  const monitor = ctx.createGain(); // 語り手が聞く（イヤホン）
  monitor.connect(ctx.destination);
  const recBus = ctx.createGain();  // 録画へ（届けている聞き手の声だけ。栓の後ろから取る。録画と練習 G1）
  const ins = new Map();   // 聞き手 id → { src, gate, an, buf, el, heard, open, until, level }
  const outs = new Map();  // 聞き手 id → { dest: MediaStreamAudioDestinationNode, nGain: 語り手の声の栓 }
  let timer = 0;

  function db(an, buf) {
    an.getFloatTimeDomainData(buf);
    let sum = 0;
    for (const v of buf) sum += v * v;
    return 10 * Math.log10(sum / buf.length + 1e-12);
  }

  function apply(id) {
    const x = ins.get(id);
    if (!x) return;
    const v = x.heard && x.open ? 1 : 0;
    x.gate.gain.setTargetAtTime(v, ctx.currentTime, v ? 0.01 : 0.08);
  }

  function tick() {
    const now = performance.now();
    for (const [id, x] of ins) {
      x.level = db(x.an, x.buf);
      if (x.level > GATE_DB) x.until = now + GATE_HOLD_MS;
      const open = now < x.until;
      if (open !== x.open) { x.open = open; apply(id); }
    }
  }

  /** 出口を作る（承認した聞き手ごと）。返す流れを声の通話で送る。
   *  語り手の声は出口ごとの栓（nGain）を通す——語り手と同じ部屋の端末へだけ止められるように（voice.js の quiet） */
  function output(id) {
    if (outs.has(id)) return outs.get(id).dest.stream;
    const dest = ctx.createMediaStreamDestination();
    const nGain = ctx.createGain();
    nGain.gain.value = 1;
    narrator.gain.connect(nGain);
    nGain.connect(dest);
    outs.set(id, { dest, nGain });
    for (const [other, x] of ins) if (other !== id) x.gate.connect(dest);
    return dest.stream;
  }

  return {
    /** 語り手のマイク */
    setNarrator(stream) {
      if (narrator.src) narrator.src.disconnect();
      narrator.stream = stream;
      narrator.src = stream ? ctx.createMediaStreamSource(stream) : null;
      if (narrator.src) narrator.src.connect(narrator.gain);
    },
    output,
    /** 聞き手の声の入口 */
    input(id, stream) {
      this.drop(id, true);
      const src = ctx.createMediaStreamSource(stream);
      const gate = ctx.createGain();
      gate.gain.value = 0;
      const an = ctx.createAnalyser();
      an.fftSize = 1024;
      src.connect(an);
      src.connect(gate);
      gate.connect(monitor);
      gate.connect(recBus);
      const el = new Audio(); // keepAlive（上の ⚠️）
      el.muted = true;
      el.srcObject = stream;
      el.play().catch(() => {});
      const x = { src, gate, an, buf: new Float32Array(an.fftSize), el, heard: false, open: false, until: 0, level: -120 };
      ins.set(id, x);
      for (const [other, o] of outs) if (other !== id) gate.connect(o.dest);
      if (!timer) timer = setInterval(tick, 50);
    },
    /** 聞き手が去った。keepOut＝出口は残す（入口だけ張り直すとき） */
    drop(id, keepOut = false) {
      const x = ins.get(id);
      if (x) { x.src.disconnect(); x.gate.disconnect(); x.el.srcObject = null; ins.delete(id); }
      if (!keepOut && outs.has(id)) { const { dest: d, nGain } = outs.get(id); narrator.gain.disconnect(nGain); nGain.disconnect(); for (const y of ins.values()) { try { y.gate.disconnect(d); } catch { /* つながっていない */ } } outs.delete(id); }
      if (!ins.size) { clearInterval(timer); timer = 0; }
    },
    /** 届ける声の一覧（voice.js の routes().narrator）。ほかは栓を閉める */
    setHeard(ids) {
      const set = new Set(ids);
      for (const [id, x] of ins) { x.heard = set.has(id); apply(id); }
    },
    /** 聞き手ごとに、語り手の声を届けるか（voice.js の routes().listeners[id].narrator）。語り手と同じ部屋の端末へだけ止める */
    setNarratorTo(map) {
      for (const [id, o] of outs) {
        const v = map[id] && map[id].narrator === false ? 0 : 1;
        o.nGain.gain.setTargetAtTime(v, ctx.currentTime, v ? 0.01 : 0.05);
      }
    },
    /** 語り手の自分のマイク（V11）。マイクそのものの音を切る（聞き手へも、点呼の測りへも行かない） */
    setNarratorMic(on) { if (narrator.stream) for (const tr of narrator.stream.getAudioTracks()) tr.enabled = !!on; },
    /** 語り手が聞き手の声を聞くか（語り手の端末の音） */
    setMonitor(on) { monitor.gain.value = on ? 1 : 0; },
    /** 聞き手ごとの声の大きさ（dB）と、話しているか（札の印） */
    levels() {
      const out = {};
      for (const [id, x] of ins) out[id] = { db: x.level, speaking: x.level > SPEAK_DB };
      return out;
    },
    /** 録画用の取り出し口: 届けている聞き手の声（語り手の声は入れない——録画はマイクから直に取る） */
    tap() {
      const d = ctx.createMediaStreamDestination();
      recBus.connect(d);
      return { stream: d.stream, close: () => { try { recBus.disconnect(d); } catch { /* 外し済み */ } } };
    },
    has: (id) => ins.has(id),
    /** 出口ごとの語り手の声の栓（自動テスト用） */
    narratorGains: () => Object.fromEntries([...outs].map(([id, o]) => [id, o.nGain.gain.value])),
    get narratorStream() { return narrator.stream; },
  };
}
