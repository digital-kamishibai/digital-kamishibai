// TURN の認証情報まわりの純粋な関数（Worker と node --test の両方から使う）。

/** Cloudflare の応答（配列でも1件の物でもよい）を RTCPeerConnection の iceServers に整える。
 *  ⚠️ ポート53の URL は落とす——ブラウザが塞いでいて、時間切れまで待たされる（Cloudflare の文書）。 */
export function normalizeIceServers(body) {
  const raw = body && body.iceServers;
  const list = Array.isArray(raw) ? raw : raw ? [raw] : [];
  const out = [];
  for (const s of list) {
    const urls = (Array.isArray(s.urls) ? s.urls : [s.urls]).filter((u) => typeof u === 'string' && !/:53(\?|$)/.test(u));
    if (!urls.length) continue;
    const entry = { urls };
    if (s.username) entry.username = s.username;
    if (s.credential) entry.credential = s.credential;
    out.push(entry);
  }
  return out;
}

/** 同じサイトのページからの要求か（ブラウザが付ける見出しで見る。ブラウザ以外は偽れるので、守りは回数制限と期限と組み合わせる） */
export function isSameOrigin(request) {
  const site = request.headers.get('Sec-Fetch-Site');
  if (site) return site === 'same-origin';
  const origin = request.headers.get('Origin');
  if (origin) return origin === new URL(request.url).origin;
  return false;
}
