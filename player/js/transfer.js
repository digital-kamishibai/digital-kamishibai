// 動画の受け渡しの計算。DOM にも通信にも保存にも触らない純粋な関数だけを置く（node --test で守る）。
// 設計: 本リポのプラン「段階2の実装設計」#2〜#5・#7・#8。

export const CHUNK = 64 * 1024;              // 1回に送る大きさ（ブラウザの間で安全なメッセージの大きさ）
export const SEGMENT = 4 * 1024 * 1024;      // 受け手が端末へ書く単位。書けた区切りまでが「持っている分」
export const SEND_HIGH = 8 * 1024 * 1024;    // 送り待ちがこれを超えたら止める
export const SEND_LOW = 1024 * 1024;         // ここまで減ったら再開
export const WINDOW = 16 * 1024 * 1024;      // 送ったが「書けた」と返事の来ていない分の上限（受け手のメモリを抑える）
export const SIZE_LIMIT = 300 * 1000 * 1000; // work-format.md §4（暫定）。10進で数える
export const FREE_MARGIN = 50 * 1000 * 1000; // 空き容量の余裕

/** 持っている分を、書けた区切りに切り詰める（途中の区切りは端末に無い） */
export function storedBytes(bytes, size) {
  const b = Math.max(0, Math.min(Number(bytes) || 0, size));
  return b === size ? size : Math.floor(b / SEGMENT) * SEGMENT;
}

/** 動画が配れる形か（§4: MP4・上限内）。配れないなら理由 */
export function sendable(item, limit = SIZE_LIMIT) {
  if (item.kind === 'audio') {
    if (!/\.(mp3|m4a)$/i.test(item.key || '')) return 'not-audio';
  } else if (!/\.mp4$/i.test(item.key || '')) return 'not-mp4';
  if (item.size > limit) return 'too-big';
  return null;
}

/** 端末ごとの方式を選ぶ。have = 聞き手の申告 { store, free, items:[{id, bytes}] }
 *  戻り値: [{ id, mode: 'stored'|'stream', from, reason }]（from = 送り始める位置。size なら送り済み） */
export function planTransfers(videos, have, limit = SIZE_LIMIT) {
  const items = new Map(((have && have.items) || []).map((i) => [i.id, i.bytes]));
  let free = have && Number.isFinite(have.free) ? have.free : Infinity;
  return videos.map((v) => {
    const bad = sendable(v, limit);
    if (bad) return { id: v.id, mode: 'stream', from: 0, reason: bad };
    if (!have || !have.store) return { id: v.id, mode: 'stream', from: 0, reason: 'no-store' };
    const from = storedBytes(items.get(v.id), v.size);
    const need = v.size - from;
    if (need > 0 && need + FREE_MARGIN > free) return { id: v.id, mode: 'stream', from, reason: 'no-space' };
    free -= need;
    return { id: v.id, mode: 'stored', from, reason: null };
  });
}

/** 送り手の待ち: 送り待ちが多すぎる、または返事の来ていない分が窓を超えた */
export function mustWait(buffered, sent, acked) {
  return buffered > SEND_HIGH || sent - acked >= WINDOW;
}

// ---------- 絵の送り出し（2026-10-25 設計 D1・D2） ----------
// 絵を続けて送ると、後から送った枚の合図が送り待ちの絵の後ろに並ぶ（実際の作品の約10MB で 8.5秒遅れた）。
// 送り待ちが小さくなってから1枚ずつ送り、合図が待つのを送りかけの1枚ぶんまでにする

export const PIC_LOW = 64 * 1024; // 合図用の接続の送り待ちがここまで減ったら、次の絵を送る

/** 次の絵を送ってよいか（PeerJS の列が空で、ブラウザの列が PIC_LOW 以下） */
export const picReady = (buffered, peerBuffer) => !(peerBuffer > 0) && !(buffered > PIC_LOW);

/** 送り待ちの絵の中から、次に送る1枚: いまの枚 → その先（近い順）→ 前の枚（近い順）。無ければ null */
export function nextPicture(pending, cur) {
  let best = null, key = Infinity;
  for (const n of pending) {
    const k = n >= cur ? n - cur : 1e6 + (cur - n);
    if (k < key) { key = k; best = n; }
  }
  return best;
}

/** 受け手: 1区切りぶん溜まったか（最後の端切れは size で判定） */
export function segmentReady(pending, offset, size) {
  return pending >= SEGMENT || offset + pending >= size;
}

/** 受け取りの様子（語り手の画面と待ち時間の記録用） */
export function progress(bytes, size, startedAt, now, startBytes = 0) {
  const sec = Math.max(0.001, (now - startedAt) / 1000);
  const rate = (bytes - startBytes) / sec; // バイト/秒
  return {
    pct: size ? Math.floor((bytes / size) * 100) : 100,
    mbps: rate / 1e6,
    eta: rate > 0 ? Math.ceil((size - bytes) / rate) : null,
  };
}

export function fmtMB(bytes) {
  return `${Math.round(bytes / 1e6)}MB`;
}

export function fmtTime(sec) {
  if (sec == null || !Number.isFinite(sec)) return '—';
  const s = Math.max(0, Math.round(sec));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}
