// 声（段階3）の取り決めと判定。プラン「段階3の実装設計」V1〜V10。
// DOM にも通信にも触らない純粋な関数だけを置く（node --test で守る）。
// 声は語り手を真ん中にした星形で運ぶ（V1）。ここが決めるのは「誰の声を誰へ届けるか」だけで、運び方は知らない
// ——運び方を全結線や外の中継に変えても、この表とテストはそのまま残す（2026-10-24 の決定）。

export const MICS = ['on', 'off', 'listen', 'denied', 'none'];

/** 語り手の側の声の状態 */
export function createVoice() {
  return {
    narratorMic: true,      // 語り手の自分のマイク（V11）
    allHeld: false,         // 「聞き手の声: まとめて届けない」（V5）
    held: new Set(),        // 語り手が札で「届けない」にした聞き手
    sameRoom: new Set(),    // 音の点呼で同じ部屋と分かった、後から入ったほう（V9。語り手が戻せる）
    quiet: new Set(),       // 語り手と同じ部屋と分かった聞き手——その端末では語り手の声を鳴らさない（ハウリング止め。語り手も本人も戻せる）
    bgmHold: false,         // BGM のあいだは聞き手の声を届けない（V7。決定: 最初は届ける）
  };
}

/** 聞き手 j の声をいま届けるか。ctx: { video（動画を再生中）, bgm（BGM が鳴っている） }。
 *  戻り値 { heard, reason }。reason は届かない理由（札と聞き手の画面に出す）:
 *   'mic'（本人がマイクを使っていない・切っている）/ 'video' / 'bgm' / 'held'（語り手が止めた）/ 'same-room' */
export function heardFrom(peer, voice, ctx = {}) {
  if (!peer || peer.status !== 'approved') return { heard: false, reason: 'not-approved' };
  const mic = peer.view && peer.view.mic;
  if (mic !== 'on') return { heard: false, reason: 'mic' };
  if (voice.sameRoom.has(peer.id)) return { heard: false, reason: 'same-room' };
  if (voice.allHeld || voice.held.has(peer.id)) return { heard: false, reason: 'held' };
  if (ctx.video) return { heard: false, reason: 'video' };      // V6: 動画のあいだは自動で届けない
  if (ctx.bgm && voice.bgmHold) return { heard: false, reason: 'bgm' };
  return { heard: true, reason: null };
}

/** 届け先の表（V1）。承認済みの聞き手 i ごとに「語り手の声を聞くか」と「誰の声を聞くか」。
 *  自分の声は自分に返さない。承認していない端末は表に入らない（R7）。narrator＝語り手が聞く声 */
export function routes(peers, voice, ctx = {}) {
  const approved = [...peers.values()].filter((p) => p.status === 'approved');
  const heard = approved.filter((p) => heardFrom(p, voice, ctx).heard).map((p) => p.id);
  const out = { narrator: heard, listeners: {} };
  for (const p of approved) {
    out.listeners[p.id] = { narrator: !!voice.narratorMic && !voice.quiet.has(p.id), from: heard.filter((id) => id !== p.id) };
  }
  return out;
}

/** 聞き手へ「いまあなたの声は届いているか」「語り手の声を鳴らさないでいるか（quiet）」を知らせる合図。
 *  前に知らせたもの（prev: id → 'heard|reason|quiet'）と違う端末にだけ */
export function voiceMessages(peers, voice, ctx, prev) {
  const out = [];
  for (const p of peers.values()) {
    if (p.status !== 'approved') continue;
    const h = heardFrom(p, voice, ctx);
    const quiet = voice.quiet.has(p.id);
    const key = `${h.heard}|${h.reason}|${quiet}`;
    if (prev.get(p.id) === key) continue;
    prev.set(p.id, key);
    out.push({ to: p.id, msg: { t: 'voice', heard: h.heard, reason: h.reason, quiet } });
  }
  return out;
}

// ---------- 音の点呼（V8・V9） ----------

export const TONE_HZ = 1800;     // 確かめの音の高さ（声と BGM に埋もれにくい高さ）
export const TONE_MS = 300;
export const TONE_DB = 18;       // その高さの音が、まわりの音より何 dB 大きければ「拾った」とみなすか

/** 周波数ごとの大きさ（dB の配列）から、確かめの音の高さが、まわり（中央値）より何 dB 大きいか */
export function toneLevel(freqDb, sampleRate, fftSize, hz = TONE_HZ) {
  const n = freqDb.length;
  if (!n) return 0;
  const bin = Math.round((hz * fftSize) / sampleRate);
  let peak = -Infinity;
  for (let i = Math.max(0, bin - 2); i <= Math.min(n - 1, bin + 2); i++) peak = Math.max(peak, freqDb[i]);
  const sorted = [...freqDb].filter(Number.isFinite).sort((a, b) => a - b);
  if (!sorted.length || !Number.isFinite(peak)) return 0;
  return Math.max(0, peak - sorted[Math.floor(sorted.length / 2)]);
}

export const toneHeard = (level) => Number.isFinite(+level) && +level >= TONE_DB;

/** 点呼の順番: 語り手 → 承認済みの聞き手（入ってきた順）。音を鳴らすのにマイクは要らない——
 *  聞くだけの端末の音も語り手のマイクが拾えば、その端末のスピーカー → 語り手のマイクの輪（ハウリング）が見つかる */
export function rollOrder(peers) {
  return ['narrator', ...[...peers.values()].filter((p) => p.status === 'approved').map((p) => p.id)];
}

/** 点呼の結果を判定する。results: [{ source, levels: { 測った端末の id または 'narrator': dB } }]。
 *  joined: id → 入った順（小さいほど先）。
 *  戻り値: { speaker（語り手の PC が鳴らした音を語り手のマイクが拾った＝イヤホンをしていない）,
 *           pairs: [[a, b]]（同じ部屋の組）, hold: [後から入ったほう（声を届けない）],
 *           quiet: [語り手と同じ部屋の聞き手（その端末では語り手の声を鳴らさない）] } */
export function judgeRollCall(results, joined) {
  let speaker = false;
  const pairs = [];
  const seen = new Set();
  for (const r of results) {
    for (const [who, level] of Object.entries(r.levels || {})) {
      if (!toneHeard(level)) continue;
      if (who === r.source) { if (who === 'narrator') speaker = true; continue; }
      const key = [r.source, who].sort().join('\u0000');
      if (seen.has(key)) continue;
      seen.add(key);
      pairs.push([r.source, who]);
    }
  }
  const order = (id) => (id === 'narrator' ? -1 : joined.has(id) ? joined.get(id) : Infinity);
  // 語り手は止められない（語りが消える）ので、語り手と同じ部屋なら聞き手のほうを止める
  const hold = [...new Set(pairs.map(([a, b]) => (order(a) > order(b) ? a : b)).filter((id) => id !== 'narrator'))];
  // 語り手と同じ部屋の聞き手のスピーカーから語り手の声が出ると、語り手のマイクが拾って輪になる（2026-11-02 実機でハウリング）。
  // 語り手のマイクは止められない（遠くの聞き手に届かなくなる）ので、その端末で語り手の声を鳴らさない——生の声が聞こえている
  const quiet = [...new Set(pairs.filter((pr) => pr.includes('narrator')).map(([a, b]) => (a === 'narrator' ? b : a)))];
  return { speaker, pairs, hold, quiet };
}
