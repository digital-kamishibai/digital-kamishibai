// 語り手の画面の作り直し（プラン「語り手の画面の作り直し」U1〜U5）の取り決めと判定。
// DOM にも通信にも触らない純粋な関数だけを置く（node --test で守る）。
//   - 聞き手 → 語り手の報告 `view`（聞き手の端末が、いま自分の画面に何を出しているか）
//   - 聞き手ごとの札の判定（語り手の枚と食い違う・タップ待ち）
//   - 語り手の画面の切り替え（準備 → 受付 → 上演）

export const SHOWS = ['picture', 'video', 'stream', 'waiting'];
export const SOUNDS = ['on', 'tap', 'none'];
export const MICS = ['on', 'off', 'listen', 'denied', 'none']; // 段階3 V10（voice.js と同じ並び）

const num = (v) => (Number.isFinite(+v) && +v >= 0 ? Math.floor(+v) : 0);

/** 聞き手の画面の状態 → 報告の合図。**中身は状態の名前と数だけ**（絵そのものは送らない）。
 *  st: { slide, picture, video: null | { local, stream, playing }, waiting, sound, recv: { got, all } }
 *   - video: 動画を出している（local＝自分の保存した動画・stream＝語り手の映像）
 *   - waiting: 語り手が動画を始めたが、まだ出せていない（受け取り中・映像を待っている）。または今の枚の絵がまだ無い */
export function makeView(st) {
  let show = 'waiting';
  if (st.video && st.video.local) show = 'video';
  else if (st.video && st.video.stream) show = 'stream';
  else if (!st.waiting && st.picture) show = 'picture';
  const msg = { t: 'view', slide: num(st.slide), show, sound: SOUNDS.includes(st.sound) ? st.sound : 'none', mic: MICS.includes(st.mic) ? st.mic : 'none' };
  if (show === 'video' || show === 'stream') msg.playing = !!(st.video && st.video.playing);
  const recv = st.recv || {};
  msg.recv = { got: Math.min(num(recv.got), num(recv.all)), all: num(recv.all) };
  return msg;
}

/** 前に送った報告と比べて、送り直す必要があるか（画面が変わったときだけ送る） */
export function viewChanged(prev, next) {
  return !prev || JSON.stringify(prev) !== JSON.stringify(next);
}

/** 語り手が受け取った報告を、知っている項目だけで作り直す（変なものが来ても札が壊れないように）。
 *  形が違えば null */
export function cleanView(msg) {
  if (!msg || msg.t !== 'view' || !Number.isInteger(msg.slide) || msg.slide < 1) return null;
  if (!SHOWS.includes(msg.show) || !SOUNDS.includes(msg.sound)) return null;
  // mic は段階3で足した。送ってこない古い聞き手は「マイクが無い」として扱う
  const v = { slide: msg.slide, show: msg.show, sound: msg.sound, mic: MICS.includes(msg.mic) ? msg.mic : 'none' };
  if (msg.show === 'video' || msg.show === 'stream') v.playing = !!msg.playing;
  const r = msg.recv && typeof msg.recv === 'object' ? msg.recv : {};
  const all = num(r.all);
  v.recv = { got: Math.min(num(r.got), all), all };
  return v;
}

/** 語り手から見て、聞き手の画面に出ているはずのもの。expect: { slide, video }（video＝語り手が動画を始めている） */
export function expectedShow(expect) {
  return expect.video ? 'video' : 'picture';
}

/** 聞き手の札の判定。戻り値 { level: 'ok' | 'warn' | 'unknown', slide, show, sound, receiving }
 *   - slide: 語り手の枚と食い違う
 *   - show: 絵を出すはずが動画（またはその逆）・準備中
 *   - sound: 音がタップ待ち
 *  報告がまだ無い端末は unknown（承認した直後・古い版の聞き手） */
export function chipState(view, expect) {
  if (!view) return { level: 'unknown', slide: false, show: false, sound: false, receiving: false };
  const slide = view.slide !== expect.slide;
  const want = expectedShow(expect);
  const isVideo = view.show === 'video' || view.show === 'stream';
  const show = !slide && (want === 'video' ? !isVideo : view.show !== 'picture');
  const sound = view.sound === 'tap';
  const receiving = view.recv.all > 0 && view.recv.got < view.recv.all;
  return { level: slide || show || sound ? 'warn' : 'ok', slide, show, sound, receiving };
}

// ---------- 画面の切り替え（U1） ----------

export const SCREENS = ['prep', 'room', 'show'];

/** 語り手の画面の移り。cur＝いまの画面。ev:
 *   { type: 'loaded', missing }  作品（と素材フォルダ）を読んだ。足りない素材が無ければ準備 → 受付へ
 *   { type: 'started' }          開演を押した → 上演へ
 *   { type: 'tab', to }          上の帯で選んだ（作品を読むまでは準備から動かない）
 *  ctx: { hasWork }
 *  ⚠️ 画面を移っても、ページは移らない（ページを移ると聞き手との接続が切れる） */
export function nextScreen(cur, ev, ctx = {}) {
  if (!SCREENS.includes(cur)) cur = 'prep';
  switch (ev && ev.type) {
    case 'loaded': return cur === 'prep' && !(ev.missing > 0) ? 'room' : cur;
    case 'started': return 'show';
    case 'tab': return SCREENS.includes(ev.to) && (ctx.hasWork || ev.to === 'prep') ? ev.to : cur;
    default: return cur;
  }
}

/** 上演の画面の上に出す、承認の知らせの帯（U5）。上演の画面にいるときだけ、入ろうとしている新しい端末を並べる。
 *  入り直し（合い札）の端末はその場で承認済みになるので、ここには来ない */
export function bannerFor(peers, screen) {
  if (screen !== 'show') return [];
  return [...peers.values()].filter((p) => p.status === 'pending');
}

// ---------- 1枚に動画が複数ある枚（2026-10-24 決定 B・W1〜W3） ----------

/** その枚の動画の一覧（台本に書いた順＝work.json の cues の順。resolveVideos がその順に並べている） */
export function videosOn(videos, slide) {
  return videos.filter((v) => v.n === slide);
}

/** 枠に出す1本。語り手が選んだもの（chosen＝id）がその枚に無ければ1本目。動画の無い枚は null */
export function pickVideo(list, chosen) {
  return list.find((v) => v.id === chosen) || list[0] || null;
}

/** 切り替えの前に、いま流している動画を止めて聞き手の画面を絵へ戻すか（W2）。
 *  playingId＝語り手が始めている動画（一時停止中も含む）。同じ1本を選び直したときは止めない */
export function mustStopFor(next, playingId) {
  return !!playingId && (!next || next.id !== playingId);
}

/** 切り替えのボタンに出す短い名前（パスとファイルの種類を落とす）。長いものは切る */
export function videoName(key, max = 28) {
  const base = String(key || '').split('/').pop().replace(/\.[^.]+$/, '');
  return base.length > max ? base.slice(0, max - 1) + '…' : base;
}

// ---------- 上演の画面の境目（U8。2026-10-25） ----------

export const SPLIT_DEFAULT = 42;  // 左（聞き手の画面）の幅 %。台本を広めに
export const SPLIT_MIN = 30;
export const SPLIT_MAX = 65;
export const SPLIT_STEP = 2;      // 矢印キーの1回

/** 境目の割合をそろえる（範囲の外は端へ・数でなければ既定・小数1桁） */
export function clampSplit(v) {
  const n = Number(v);
  if (v === null || v === undefined || v === '' || !Number.isFinite(n)) return SPLIT_DEFAULT;
  return Math.round(Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, n)) * 10) / 10;
}

/** ドラッグした位置 → 割合（x は画面の座標、left・width は境目を含む2列ぶんの箱） */
export const splitAt = (x, left, width) => clampSplit(width > 0 ? ((x - left) / width) * 100 : SPLIT_DEFAULT);
