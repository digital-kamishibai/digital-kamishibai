// 動画の再生の合図。語り手が押した「再生・一時停止・頭出し」を、各端末が自分の動画で再現する。
// DOM にも通信にも触らない純粋な関数だけを置く（node --test で守る）。設計: プラン「段階2の実装設計」#6・#11。

export const TOLERANCE = 1;      // 秒。これ以上ずれた端末だけ頭出しで合わせる（細かい揃え込みはしない）
export const TICK_MS = 5000;     // 再生中に語り手の位置を送る間隔

/** 語り手の側の状態。id = いま扱っている動画（無ければ null） */
export function createPlayback() {
  return { id: null, playing: false, pos: 0, at: 0 };
}

/** いまの位置（再生中なら、合図のときからの経過を足す） */
export function positionAt(st, now) {
  return st.playing ? st.pos + Math.max(0, now - st.at) / 1000 : st.pos;
}

/** 語り手の操作 → 新しい状態。action: 'play' | 'pause' | 'seek' | 'stop' */
export function command(st, action, { id = st.id, pos, now }) {
  const here = pos != null ? Math.max(0, pos) : positionAt(st, now);
  switch (action) {
    case 'play': return { id, playing: true, pos: here, at: now };
    case 'pause': return { id, playing: false, pos: here, at: now };
    case 'seek': return { id, playing: st.playing, pos: here, at: now };
    case 'stop': return createPlayback();
    default: return st;
  }
}

/** 聞き手へ送る合図（状態そのもの。途中から入った端末にも同じものを送ればよい）。
 *  `playing` は BGM を下げる合図の土台にもなる（段階4） */
export function vstate(st, now) {
  return { t: 'vstate', id: st.id, playing: st.playing, pos: positionAt(st, now) };
}

/** 聞き手: 合図を受けて、自分の動画に何をするか。local = { pos, paused }
 *  戻り値: { show, seek: 秒|null, play: true|false|null } */
export function apply(local, msg, tolerance = TOLERANCE) {
  if (!msg || !msg.id) return { show: false, seek: null, play: false };
  const drift = Math.abs((local ? local.pos : 0) - msg.pos);
  // 再生中は1秒以上のずれだけ合わせる。一時停止中は小さくても合わせる（止まった絵が語り手と違うと気づかれる）
  const seek = (msg.playing ? drift >= tolerance : drift > 0.05) ? msg.pos : null;
  let play = null;
  if (msg.playing && (!local || local.paused)) play = true;
  if (!msg.playing && local && !local.paused) play = false;
  return { show: true, seek, play };
}

/** 動画が鳴っているか（BGM を下げる判断の土台） */
export const ducking = (st) => !!(st && st.id && st.playing);
