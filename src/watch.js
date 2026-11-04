// 中継（TURN）の見張り。Cron（5分おき）から呼ぶ。判定は guard.js の純粋な関数、ここは照会・KV・取り消しの通信だけ。
import { readCaps, readDonation, donationKey, DONATION_MAX_USD, decide, pickRevokes, USAGE_QUERY, usageVariables, readUsage } from './guard.js';

export const TTL = 4 * 60 * 60; // 認証情報の期限＝4時間（開演前の準備＋上演＋余裕）
export const MARK = 'status'; // KV の印（配る／配らない・理由・付けた時刻）
const REVOKED = 'revoked:'; // 取り消した認証情報の印（認証情報の期限と同じ4時間で消える）
const REVOKE_MAX = 40; // 1回で取り消す数（無料プランは1回の外向き通信が50回まで。照会の1回を含めて余裕を残す）
const CHECK_MAX = 500; // 取り消し済みかを KV で確かめる数の上限（内向きの呼び出しは1回1,000まで）

/** 見張り（Cron 5分おき）: 照会 → 判定 → 印 → 取り消し。
 *  印を取り消しより先に付ける——入口が止まるのを取り消しの待ちで遅らせない。
 *  照会に失敗したら印を新しくしない（30分で入口が自分で止まる。決定 A）。鍵が無い箱（開発用）では何もしない。 */
export async function watch(env, now = Date.now(), fetcher = fetch) {
  if (!env.TURN_KEY_ID || !env.TURN_KEY_API_TOKEN) return { skipped: 'no-turn-key' };
  if (!env.TURN_GUARD || !env.CF_ANALYTICS_TOKEN || !env.CF_ACCOUNT_ID) {
    console.error('turn guard: TURN_GUARD / CF_ANALYTICS_TOKEN / CF_ACCOUNT_ID is missing — relay stays off');
    return { skipped: 'no-guard-config' };
  }
  const res = await fetcher('https://api.cloudflare.com/client/v4/graphql', {
    method: 'POST',
    headers: { Authorization: `Bearer ${env.CF_ANALYTICS_TOKEN}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: USAGE_QUERY, variables: usageVariables({ accountTag: env.CF_ACCOUNT_ID, keyId: env.TURN_KEY_ID, now }) }),
  });
  if (!res.ok) throw new Error(`turn guard: graphql ${res.status}`);
  const usage = readUsage(await res.json());
  const raw = await env.TURN_GUARD.get(donationKey(now));
  const donation = readDonation(raw);
  if (raw !== null && raw !== undefined && donation === 0 && Number(raw) !== 0) {
    console.error(`turn guard: ${donationKey(now)} is not a number from 0 to ${DONATION_MAX_USD} — counted as 0`);
  }
  const caps = readCaps(env, donation);
  const d = decide(usage, caps);
  await env.TURN_GUARD.put(MARK, JSON.stringify({
    serve: d.serve, reason: d.reason, at: now,
    month: usage.month, day: usage.day, caps, donation,
  }));
  const revoked = new Set();
  for (const u of d.revoke.slice(0, CHECK_MAX)) {
    if (await env.TURN_GUARD.get(REVOKED + u)) revoked.add(u);
  }
  const done = [];
  for (const u of pickRevokes(d.revoke.slice(0, CHECK_MAX), revoked, REVOKE_MAX)) {
    const r = await fetcher(`https://rtc.live.cloudflare.com/v1/turn/keys/${env.TURN_KEY_ID}/credentials/${encodeURIComponent(u)}/revoke`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${env.TURN_KEY_API_TOKEN}` },
    });
    if (r.ok || r.status === 404) { // 404＝もう無い（期限切れ）。何度も試さない
      await env.TURN_GUARD.put(REVOKED + u, '1', { expirationTtl: TTL });
      done.push(u);
    } else {
      console.error(`turn guard: revoke ${r.status}`);
    }
  }
  return { serve: d.serve, reason: d.reason, revoked: done.length, pending: d.revoke.length - revoked.size - done.length };
}
