// Cloudflare Worker。player/ の静的ファイルを配り、/api/ice でだけ TURN の認証情報を渡す。
// 絵・動画・声はここを通らない（端末どうし、つながらなければ Cloudflare の TURN が暗号化されたまま中継する）。
// 5分おきの見張り（scheduled）が中継の使用量を照会し、損失の天井（guard.js）を超えたら取り消しと「配らない」の印を付ける。
import { normalizeIceServers, isSameOrigin } from './ice.js';
import { gate } from './guard.js';
import { watch, MARK, TTL } from './watch.js';

const STUN_ONLY = [{ urls: ['stun:stun.cloudflare.com:3478'] }];

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' },
  });
}

async function ice(request, env) {
  if (request.method !== 'GET') return json({ error: 'method' }, 405);
  if (!isSameOrigin(request)) return json({ error: 'origin' }, 403);
  if (env.ICE_LIMIT) {
    const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
    const { success } = await env.ICE_LIMIT.limit({ key: ip });
    if (!success) return json({ error: 'rate' }, 429);
  }
  // 鍵が未設定なら STUN だけ返す（同じネットワークの中なら、それでつながる）
  if (!env.TURN_KEY_ID || !env.TURN_KEY_API_TOKEN) return json({ iceServers: STUN_ONLY, turn: false });
  // 損失の天井: 見張りの印を読むだけ（入口を遅くしない）。印が無い・30分以上古い・枠を超えた なら配らない
  let mark = null;
  try { mark = env.TURN_GUARD ? await env.TURN_GUARD.get(MARK, 'json') : null; } catch { /* 読めない＝効いているか分からない */ }
  const g = gate(mark, Date.now());
  if (!g.serve) return json({ iceServers: STUN_ONLY, turn: false, ...(g.reason ? { reason: g.reason } : {}) });
  const res = await fetch(`https://rtc.live.cloudflare.com/v1/turn/keys/${env.TURN_KEY_ID}/credentials/generate-ice-servers`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${env.TURN_KEY_API_TOKEN}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ ttl: TTL }),
  });
  if (!res.ok) return json({ iceServers: STUN_ONLY, turn: false, error: `turn ${res.status}` });
  const servers = normalizeIceServers(await res.json());
  return json({ iceServers: servers.length ? servers : STUN_ONLY, turn: servers.some((s) => s.username) });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/api/ice') return ice(request, env);
    return env.ASSETS.fetch(request);
  },
  async scheduled(controller, env, ctx) {
    ctx.waitUntil(watch(env).then((r) => console.log('turn guard', JSON.stringify(r))));
  },
};
