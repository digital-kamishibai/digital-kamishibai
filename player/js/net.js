// 通信の層。紹介役（PeerJS の公開サーバー）につなぐところだけを持つ。誰に何を送るかは protocol.js が決める。

import { t } from './i18n.js';
import { summarizeIce, keepLast, routeOf, forcedRelay } from './ice.js';

const Peer = window.Peer || (window.peerjs && window.peerjs.Peer);

// 紹介役の上の ID の接頭辞。合言葉（数字6桁）はこの後ろに付く＝合言葉が ID そのもの（r7）。
// 守りは語り手の承認であって、合言葉の秘密さではない。
export const ID_PREFIX = 'dk-room-v1-';

// 端末どうしの道の探し方。まず直接（host・srflx）を試し、だめなら Cloudflare の TURN が中継する。
// TURN の認証情報は自分のサイトの /api/ice が短い期限つきで渡す（鍵はページに置かない）。
// ⚠️ PeerJS の既定の中継サーバー（PeerJS 社の TURN）は使わない——必ず iceServers を上書きする。
// 2026-10-22: 有線の PC と Wi-Fi のスマートフォンが別々のネットワークにいる家でつながらず、TURN を入れると決めた。
const STUN_ONLY = [{ urls: 'stun:stun.cloudflare.com:3478' }];
let iceCache = null;
let relay = false; // /api/ice が中継（TURN）の認証情報を配ったか。案内の文を選ぶのに使う（ice.js の whyBlocked）
let relayReason = null; // 中継を止めている理由（'month' | 'day'。損失の天井）。案内は ice.js の relayNote

async function peerOptions() {
  if (!iceCache) {
    try {
      const res = await fetch('/api/ice', { cache: 'no-store' });
      const body = res.ok ? await res.json() : null;
      iceCache = body && Array.isArray(body.iceServers) && body.iceServers.length ? body.iceServers : STUN_ONLY;
      relay = !!(body && body.turn === true && iceCache !== STUN_ONLY);
      relayReason = !relay && body && (body.reason === 'month' || body.reason === 'day') ? body.reason : null;
    } catch {
      iceCache = STUN_ONLY; // 手元の確認用サーバーなど /api/ice が無いとき
    }
  }
  return { debug: 1, config: { iceServers: iceCache, ...forcedRelay(location.search, relay) } };
}

export function newCode() {
  const a = new Uint32Array(1);
  crypto.getRandomValues(a);
  return String(a[0] % 1000000).padStart(6, '0');
}

export const isCode = (s) => /^\d{6}$/.test(s);

/** 語り手: 合言葉を ID にして紹介役に登録する。使用中なら作り直す。 */
export async function openRoom(tries = 5) {
  const options = await peerOptions();
  return new Promise((resolve, reject) => {
    const code = newCode();
    const peer = new Peer(ID_PREFIX + code, options);
    peer.once('open', () => resolve({ peer, code }));
    peer.once('error', (err) => {
      peer.destroy();
      if (err.type === 'unavailable-id' && tries > 1) openRoom(tries - 1).then(resolve, reject);
      else reject(err);
    });
  });
}

/** 聞き手: 自分の ID は紹介役に任せる（推測されても困らない）。 */
export async function joinPeer() {
  const options = await peerOptions();
  return new Promise((resolve, reject) => {
    const peer = new Peer(options);
    peer.once('open', () => resolve(peer));
    peer.once('error', reject);
  });
}

/** 紹介役との接続が切れたら（端末の消灯など）つなぎ直す。上演中の端末どうしの接続は保たれる。 */
export function keepSignaling(peer) {
  peer.on('disconnected', () => {
    setTimeout(() => { if (!peer.destroyed && peer.disconnected) peer.reconnect(); }, 1000);
  });
}

/** マイクの許可をもらう。許可されたページでは、ブラウザが端末のローカル IP を隠さなくなる（mDNS の .local にしない）。
 *  隠したままだと、相手が .local を読み解けない端末（Android など）では、ルーター経由の遠回り（ヘアピン接続）に
 *  頼ることになり、多くの家庭用ルーターでつながらない（プランの r4）。マイクは段階3の声でどのみち使う。
 *  ⚠️ 流れ（stream）は止めずに持っておく——止めると、ブラウザによっては隠す動作に戻る。 */
export async function allowLocalAddress() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    for (const tr of stream.getAudioTracks()) tr.enabled = false; // 段階3までは音を使わない
    return stream;
  } catch {
    return null;
  }
}

/** つながりかけの接続の ICE の様子。確認の往復を数え、失敗して統計が消えても前回の数を残す（ice.js）。 */
export async function iceState(conn) {
  const pc = conn && conn.peerConnection;
  if (!pc) return null;
  let now = { state: pc.iceConnectionState, pairs: 0, sent: 0, answered: 0, heard: 0, local: {} };
  try { now = summarizeIce(await pc.getStats(), pc.iceConnectionState); } catch { /* 取れない端末 */ }
  conn.dkIce = keepLast(conn.dkIce, now);
  return conn.dkIce;
}

/** 中継を使える状態か（受付を開いた・入ったあとに意味を持つ） */
export const relayOffered = () => relay;

/** 中継を止めている理由（'month' | 'day' | null） */
export const relayPaused = () => relayReason;

/** つながった接続の道（'direct' | 'relay' | null）。取れない端末では null */
export async function routeState(conn) {
  const pc = conn && conn.peerConnection;
  if (!pc) return null;
  try { return routeOf(await pc.getStats()); } catch { return null; }
}

/** 画面に小さく出す1行 */
export function iceLine(s) {
  if (!s) return 'ICE: —';
  const fmt = (o) => Object.entries(o).map(([k, v]) => `${k}×${v}`).join(' ') || '—';
  return `ICE: ${s.state} · ${t('iceChecks', s.sent, s.answered, s.heard)} · local ${fmt(s.local)}`;
}

export function deviceKind() {
  const ua = navigator.userAgent;
  if (/iPhone/.test(ua)) return 'iPhone';
  if (/iPad/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) return 'iPad';
  if (/Android/.test(ua)) return /Mobile/.test(ua) ? 'Android phone' : 'Android tablet';
  if (/Windows/.test(ua)) return 'Windows PC';
  if (/Macintosh/.test(ua)) return 'Mac';
  return 'Device';
}

/** 画面の消灯を止める（対応しない端末では何もしない） */
export async function keepAwake() {
  if (!('wakeLock' in navigator)) return;
  let lock = null;
  const take = async () => { try { lock = await navigator.wakeLock.request('screen'); } catch { /* 拒否されたら諦める */ } };
  await take();
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible' && (!lock || lock.released)) take(); });
}
