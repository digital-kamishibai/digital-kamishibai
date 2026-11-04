// BGM・効果音の決め方。DOM にも通信にも触らない純粋な関数だけを置く（node --test で守る）。
// 設計: 本リポのプラン「段階4の実装設計」P1〜P5。形の定義は docs/work-format.md §2.4・§3.4。

import { positionAt } from './playback.js';

export const CROSSFADE_MS = 1500;   // 曲の入れ替え
export const FADE_OUT_MS = 2000;    // [BGM stop]
export const DUCK = 0.2;            // 動画のあいだの BGM の大きさ

// ---------- 語っているあいだ BGM を下げる（plans/kamishibai-player-talk-duck.md の T1・T2。2026-10-26） ----------
export const TALK_DUCK_DB = -10;    // 話しているあいだの BGM（dB）
export const TALK_ON_DB = -45;      // マイクの大きさ（dBFS）がこれを越えたら話し始め
export const TALK_OFF_DB = -50;     // これを下回りつづけたら話し終わり
export const TALK_ON_MS = 200;      // 越えてからこれだけ続いたら（咳・物音で下げない。2026-10-26 80→200）
export const TALK_OFF_MS = 1200;    // 下回ってからこれだけ続いたら（息継ぎ・文の切れ目ごとに上下させない。2026-10-26 練習した人「戻るのが少し早い」で 700→1200）
export const TALK_DOWN_TC = 0.03;   // 下げるときの時定数（秒）。話し始めにすぐ引っ込める
export const TALK_UP_TC = 0.25;     // 戻すときの時定数（秒）。約0.75秒かけて戻る（同日 0.15→0.25）

// ⚠️ 2026-10-26 練習した人「話していないところで、音の大きさが変動する」。マイクの自動の音量合わせ（autoGainControl）は
//    黙っているあいだ部屋の雑音を持ち上げるので、決まった dBFS のしきいだけだと雑音を声と取り違える。
//    → しきいを「いまの雑音の高さ（floor）」から測る。floor は下がるのは即座・上がるのはゆっくり（話していないときだけ）
export const TALK_MARGIN_ON_DB = 12;   // 雑音よりこれだけ大きければ話し始め
export const TALK_MARGIN_OFF_DB = 6;   // 雑音よりこれだけの差を下回りつづけたら話し終わり
export const TALK_FLOOR_RISE_DB_S = 3; // 雑音の高さを上へ追う速さ（dB／秒。黙っているあいだだけ）

/** 話しているかの判定を1歩進める（0.05秒ごと）。st={ talking, since, floor, t }
 *  （since＝しきいを越えた／下回った時刻。null＝いまは越えていない。floor＝雑音の高さ（dBFS）。t＝前の時刻） */
export function talkStep(st, levelDb, now) {
  const s = st || { talking: false, since: null, floor: levelDb, t: now };
  let floor = s.floor === undefined || s.floor === null ? levelDb : s.floor;
  if (levelDb < floor) floor = levelDb;
  else if (!s.talking) floor = Math.min(levelDb, floor + TALK_FLOOR_RISE_DB_S * Math.max(0, now - (s.t ?? now)) / 1000);
  const on = Math.max(TALK_ON_DB, floor + TALK_MARGIN_ON_DB);
  const off = Math.max(TALK_OFF_DB, floor + TALK_MARGIN_OFF_DB);
  const next = (talking, since) => ({ talking, since, floor, t: now });
  if (!s.talking) {
    if (levelDb > on) {
      const since = s.since === null ? now : s.since;
      return now - since >= TALK_ON_MS ? next(true, null) : next(false, since);
    }
    return next(false, null);
  }
  if (levelDb < off) {
    const since = s.since === null ? now : s.since;
    return now - since >= TALK_OFF_MS ? next(false, null) : next(true, since);
  }
  return next(true, null);
}

/** 枚 n で鳴っているべき BGM（§3.4: 枚 1..n の合図を順に見て、最後の bgm／bgm-stop が勝つ）。
 *  戻り値: { file, loop, from } か null（from＝その曲が始まった枚）。
 *  `[BGM after video]` の曲には after: true が付く（その枚 from では動画が終わるまで鳴らさない） */
export function bgmAt(work, n) {
  let cur = null;
  for (const s of work.slides) {
    if (s.number > n) break;
    for (const c of s.cues) {
      if (c.type === 'bgm') cur = { file: c.file, loop: c.loop !== false, from: s.number, ...(c.start === 'after-video' ? { after: true } : {}) };
      if (c.type === 'bgm-stop') cur = null;
    }
  }
  return cur;
}

/** 枚 n に入ったときに鳴らす効果音（書いた順） */
export function soundsAt(work, n) {
  const s = work.slides.find((x) => x.number === n);
  return s ? s.cues.filter((c) => c.type === 'sound').map((c) => c.file) : [];
}

/** 語り手の側の状態。started＝開演を押したか（押すまでは鳴らさない＝P1）。
 *  cut＝動画を流し始めて止めた曲（{ file, from }）。次の [BGM] の合図まで鳴らし直さない */
export function createAudio() {
  return { started: false, id: null, loop: true, from: 0, playing: false, pos: 0, at: 0, cut: null };
}

const silent = (st, now, cut) => ({ ...st, id: null, playing: false, pos: 0, at: now, from: 0, cut });
const sameSong = (a, b) => !!a && !!b && a.file === b.file && a.from === b.from;

/** 枚 n での BGM を決め直す。idOf(file) → 配った素材の id（無ければ null）。
 *  同じ曲（同じ枚から始まった同じファイル）のままなら、続けて鳴らす（P3）。
 *  動画で止めた曲（cut）は、枚を移っても鳴らし直さない——別の曲の合図に来たら、その曲を鳴らす */
export function retune(st, work, n, idOf, now) {
  if (!st.started) return st;
  const want = bgmAt(work, n);
  if (sameSong(want, st.cut)) return st.id === null ? st : silent(st, now, st.cut);
  const cut = null;
  const id = want ? idOf(want.file) : null;
  if (id && st.id === id && st.from === want.from) return !st.cut ? st : { ...st, cut };
  // `[BGM after video]` の枚: 動画が終わるまでは無音（前の曲はここで止まる）。終わったら afterVideo() が鳴らす。
  //  鳴らし始めたあとは上の「同じ曲」で続く——だから枚を離れて戻れば、また動画を待つ
  if (want && want.after && want.from === n) return st.id === null && !st.cut ? st : silent(st, now, cut);
  if (!id) return st.id === null && !st.cut ? st : silent(st, now, cut);
  return { ...st, id, loop: want.loop, from: want.from, playing: true, pos: 0, at: now, cut };
}

/** 枚 n で動画を流し始めた: BGM を止め（聞き手の端末はフェードアウト）、その曲を動画のあとに鳴らし直さない。
 *  2026-10-26 練習の修正票（「動画の後、BGMを再開する必要なし」「エンディング動画を始めたら、BGMを止めてほしい」）——
 *  上演の PPTX でも BGM は動画の直前で切れるように作ってある。止めるものが無ければ st をそのまま返す */
export function cutForVideo(st, work, n, now) {
  if (!st.started || st.id === null) return st;
  const want = bgmAt(work, n);
  return silent(st, now, want ? { file: want.file, from: want.from } : null);
}

/** 枚 n の動画が最後まで流れ終わった: その枚の `[BGM after video]` を鳴らし始める（2026-10-29 実際の作品の修正票）。
 *  旧作の PPTX で「動画のあとにクリックで鳴らす」曲。鳴らすものが無ければ st をそのまま返す */
export function afterVideo(st, work, n, idOf, now) {
  if (!st.started) return st;
  const want = bgmAt(work, n);
  if (!want || !want.after || want.from !== n) return st;
  const id = idOf(want.file);
  if (!id || (st.id === id && st.from === n)) return st;
  return { ...st, id, loop: want.loop, from: n, playing: true, pos: 0, at: now, cut: null };
}

/** 開演（P1）。押した時点の枚から鳴らし始める */
export function start(st, work, n, idOf, now) {
  return retune({ ...st, started: true }, work, n, idOf, now);
}

/** 聞き手へ送る BGM の合図（状態そのもの。途中から入った端末にも同じものを送ればよい） */
export function astate(st, now) {
  return { t: 'astate', id: st.started ? st.id : null, loop: st.loop, playing: st.playing, pos: st.started ? positionAt(st, now) : 0 };
}

/** 枚に入ったときの効果音の合図（開演前は鳴らさない） */
export function soundMessages(st, work, n, idOf) {
  if (!st.started) return [];
  return soundsAt(work, n).map((f) => idOf(f)).filter(Boolean).map((id) => ({ t: 'sound', id }));
}

/** 鳴らす位置（ループする曲は長さで割った余り。1回きりの曲は長さを越えたら終わり＝null） */
export function bgmPosition(msg, duration) {
  if (!msg || !msg.id) return null;
  if (!Number.isFinite(duration) || duration <= 0) return msg.pos;
  if (msg.loop) return msg.pos % duration;
  return msg.pos < duration ? msg.pos : null;
}
