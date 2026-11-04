// 録画と練習（プラン「録画と練習」G1〜G5・P1〜P4）の取り決めと判定。
// DOM にも通信にも触らない純粋な関数だけを置く（node --test で守る）。録る仕組みそのものは recorder.js。
//   - 録る形式の選び方（MP4〔H.264＋AAC〕を優先し、録れなければ WebM。G3）
//   - 保存するファイルの名前
//   - 絵・動画を 16:9 の枠に収める位置（聞き手の画面と同じ見え方。G1）
//   - 経過時間（全体と、この枚。P3）
//   - 練習中か（受付を開いていない。P1）
// ⚠️ 練習の記録（回数・時間）はどこにも残さない（P4）。ここの時計は画面に出すためだけのもので、保存しない

/** 録る形式の候補（上から順に試す）。Chrome 155 は MP4 で録れる（2026-10-24 確認）。古い版・ほかのブラウザは WebM になる */
export const MIMES = [
  'video/mp4;codecs=avc1.42E01F,mp4a.40.2',
  'video/mp4;codecs=avc1,mp4a.40.2',
  'video/mp4',
  'video/webm;codecs=vp9,opus',
  'video/webm;codecs=vp8,opus',
  'video/webm',
];

/** isSupported(mime) → 録れるか（MediaRecorder.isTypeSupported）。戻り値 { mime, ext } か、どれも録れなければ null */
export function pickMime(isSupported) {
  for (const mime of MIMES) {
    let ok = false;
    try { ok = !!isSupported(mime); } catch { ok = false; }
    if (ok) return { mime, ext: mime.startsWith('video/mp4') ? 'mp4' : 'webm' };
  }
  return null;
}

/** 保存するファイルの名前の案（語り手が保存先を選ぶ画面で変えられる）。Windows で使えない文字は除く */
export function recordName(title, date, ext) {
  const safe = String(title || 'kamishibai').replace(/[\\/:*?"<>|\u0000-\u001f]/g, '').replace(/\s+/g, ' ').trim().slice(0, 60) || 'kamishibai';
  const p = (n) => String(n).padStart(2, '0');
  const d = `${date.getFullYear()}${p(date.getMonth() + 1)}${p(date.getDate())}-${p(date.getHours())}${p(date.getMinutes())}`;
  return `${safe}-${d}.${ext}`;
}

/** 絵・動画（sw×sh）を枠（W×H）に、縦横比を保って収める位置（聞き手の端末の object-fit: contain と同じ）。
 *  大きさが分からないもの（読み込み前）は null＝黒のまま */
export function fitRect(sw, sh, W, H) {
  if (!(sw > 0 && sh > 0 && W > 0 && H > 0)) return null;
  const k = Math.min(W / sw, H / sh);
  const w = Math.round(sw * k);
  const h = Math.round(sh * k);
  return { x: Math.round((W - w) / 2), y: Math.round((H - h) / 2), w, h };
}

/** 枠に何を描くか。聞き手の画面と同じ決め方（語り手の画面の「聞き手の画面」の枠 U2 と同じ）:
 *   - 語り手が動画を始めている（一時停止中も）→ 動画
 *   - それ以外 → その枚の絵（絵の無い枚は黒。動画の枚の再生前も、絵があれば絵・無ければ黒）
 *  st: { videoStarted, videoReady, pictureReady } */
export function stageSource(st) {
  if (st.videoStarted && st.videoReady) return 'video';
  if (st.videoStarted) return 'black'; // 動画を始めたが、まだコマが無い（聞き手の端末も準備中）
  return st.pictureReady ? 'picture' : 'black';
}

// ---------- 経過時間（P3。本番でも出す） ----------

/** 時計。開演を押したときに全体が、枚を動かしたときに「この枚」が始まる。開演前は両方とも出さない */
export const createClock = () => ({ startedAt: null, slideAt: null });

export function clockStart(c, now) {
  if (c.startedAt != null) return c;
  return { startedAt: now, slideAt: now };
}

export function clockSlide(c, now) {
  if (c.startedAt == null) return c;
  return { ...c, slideAt: now };
}

/** 秒で返す（開演前は null） */
export function clockRead(c, now) {
  if (c.startedAt == null) return { total: null, slide: null };
  return { total: Math.max(0, (now - c.startedAt) / 1000), slide: Math.max(0, (now - c.slideAt) / 1000) };
}

// ---------- 練習（P1） ----------

/** 練習中か＝受付を開いていない（別の練習モードは作らない）。上演の画面の上に「練習中」を出すかの判定 */
export const isPractice = (ctx) => !(ctx && ctx.roomOpen);

/** 録画のボタンを押せるか。受付を開いていなくても使える（G5・P2）。作品が無い・録れないブラウザでは押せない */
export function recordable(ctx) {
  if (!ctx.hasWork) return { ok: false, why: 'no-work' };
  if (!ctx.mime) return { ok: false, why: 'no-format' };
  if (!ctx.canSave) return { ok: false, why: 'no-save' };
  return { ok: true, why: null };
}
