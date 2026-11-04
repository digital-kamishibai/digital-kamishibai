// 中継（TURN）の損失の天井まわりの純粋な関数（Worker と node --test の両方から使う）。
//
// 天井は3段: 認証情報ごと（超えたらその認証情報だけ取り消す）／1日（その日は新しく配らない）／
// 1か月（配るのをやめ、出回っている認証情報も取り消す）。日付の区切りは UTC（Cloudflare の請求の月に合わせる）。
// 数える量は egressBytes（請求の対象）。Cloudflare 側に請求の上限は無く、予算の通知は止めない——天井を守るのはこれだけ。

const GB = 1e9; // 請求の GB（10進）

/** 文字の設定値を数にする。空・数でない・負なら既定値 */
function num(v, fallback) {
  if (v === undefined || v === null || v === '') return fallback;
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 ? n : fallback;
}

/** 月の枠（バイト）＝ 無料枠 ＋（運営者の年の負担÷12 ＋ 前の月に受け取った寄付）÷ 1GB の単価。
 *  寄付はまだ受け付けていないので 0 に固定（受け付けを始めるときに、入れる口を作る）。 */
export function monthCapBytes({ freeGb = 1000, yearlyUsd = 1000, usdPerGb = 0.05, donationUsd = 0 } = {}) {
  if (!(usdPerGb > 0)) return freeGb * GB;
  return (freeGb + (yearlyUsd / 12 + donationUsd) / usdPerGb) * GB;
}

/** 設定の値（環境変数・文字）から3段の天井（バイト）を作る。数字は試験用の Worker で小さくできる。
 *  - TURN_CAP_CREDENTIAL_GB: 認証情報ごと（既定 20）
 *  - TURN_FREE_GB・TURN_YEARLY_USD・TURN_USD_PER_GB: 月の枠の式（既定 1000・1000・0.05）
 *  - TURN_CAP_MONTH_GB: 月の枠を式でなく直に決める（試験用。空なら式）
 *  - TURN_DAY_SHARE: 1日の枠＝月の枠×これ（既定 0.1） */
export function readCaps(env = {}) {
  const direct = num(env.TURN_CAP_MONTH_GB, null);
  const month = direct !== null ? direct * GB : monthCapBytes({
    freeGb: num(env.TURN_FREE_GB, 1000),
    yearlyUsd: num(env.TURN_YEARLY_USD, 1000),
    usdPerGb: num(env.TURN_USD_PER_GB, 0.05),
    donationUsd: 0,
  });
  return {
    credential: num(env.TURN_CAP_CREDENTIAL_GB, 20) * GB,
    month,
    day: month * num(env.TURN_DAY_SHARE, 0.1),
  };
}

/** 使用量 → 「配る／配らない・理由・取り消す認証情報」。境界は「超えたら」（ちょうどは配る）。
 *  usage: { month, day, credentials: [{ username, egress }] }（バイト）
 *  - 月を超えた: 配らない（'month'）。使われた認証情報はみな取り消す
 *  - 日を超えた: 配らない（'day'）。取り消すのは認証情報ごとの天井を超えたものだけ（出回っているものは期限まで使える）
 *  - どちらでもない: 配る。認証情報ごとの天井を超えたものだけ取り消す */
export function decide(usage, caps) {
  const creds = (usage.credentials || []).filter((c) => c.username);
  const over = creds.filter((c) => c.egress > caps.credential).map((c) => c.username);
  if (usage.month > caps.month) return { serve: false, reason: 'month', revoke: creds.filter((c) => c.egress > 0).map((c) => c.username) };
  if (usage.day > caps.day) return { serve: false, reason: 'day', revoke: over };
  return { serve: true, reason: null, revoke: over };
}

/** 取り消す相手のうち、まだ取り消していないものを上から max 件（無料プランは1回の外向き通信が50回まで）。 */
export function pickRevokes(candidates, alreadyRevoked, max = 40) {
  const seen = new Set();
  const out = [];
  for (const u of candidates) {
    if (out.length >= max) break;
    if (seen.has(u) || alreadyRevoked.has(u)) continue;
    seen.add(u);
    out.push(u);
  }
  return out;
}

/** 日付（UTC）の 'YYYY-MM-DD'。照会の範囲: 月の初日・今日・昨日（認証情報は4時間もつので、日をまたいだものを拾う） */
export function utcRange(now) {
  const d = new Date(now);
  const day = (x) => x.toISOString().slice(0, 10);
  const today = day(d);
  return {
    monthStart: `${today.slice(0, 8)}01`,
    today,
    yesterday: day(new Date(d.getTime() - 24 * 60 * 60 * 1000)),
  };
}

/** 1回の照会で月・日・認証情報ごとをまとめて取る（外向き通信を1回で済ませる）。
 *  月と日は箱の合計（請求は箱単位）、認証情報ごとはこの Worker の TURN の鍵の分だけ（取り消せるのは自分の鍵の認証情報だけ）。 */
export const USAGE_QUERY = `query turnGuard($accountTag: string!, $keyId: string!, $monthStart: Date!, $today: Date!, $yesterday: Date!) {
  viewer {
    accounts(filter: { accountTag: $accountTag }) {
      month: callsTurnUsageAdaptiveGroups(limit: 1, filter: { date_geq: $monthStart, date_leq: $today }) { sum { egressBytes } }
      day: callsTurnUsageAdaptiveGroups(limit: 1, filter: { date_geq: $today, date_leq: $today }) { sum { egressBytes } }
      credentials: callsTurnUsageAdaptiveGroups(limit: 1000, filter: { date_geq: $yesterday, date_leq: $today, keyId: $keyId }, orderBy: [sum_egressBytes_DESC]) {
        dimensions { username }
        sum { egressBytes }
      }
    }
  }
}`;

export function usageVariables({ accountTag, keyId, now }) {
  const r = utcRange(now);
  return { accountTag, keyId, monthStart: r.monthStart, today: r.today, yesterday: r.yesterday };
}

/** GraphQL の返事 → { month, day, credentials }。errors があるか形が違えば投げる（読めない＝効いているか分からない）。
 *  集計の組が空（まだ使われていない）なら 0。同じ username が複数の組に分かれても足す。 */
export function readUsage(body) {
  if (!body || typeof body !== 'object') throw new Error('graphql: empty');
  if (Array.isArray(body.errors) && body.errors.length) throw new Error(`graphql: ${body.errors.map((e) => e && e.message).join('; ')}`);
  const accounts = body.data && body.data.viewer && body.data.viewer.accounts;
  if (!Array.isArray(accounts) || accounts.length !== 1) throw new Error('graphql: account not found');
  const a = accounts[0];
  for (const k of ['month', 'day', 'credentials']) if (!Array.isArray(a[k])) throw new Error(`graphql: no ${k}`);
  const total = (groups) => groups.reduce((s, g) => s + bytes(g), 0);
  const byUser = new Map();
  for (const g of a.credentials) {
    const u = g.dimensions && g.dimensions.username;
    if (!u) continue;
    byUser.set(u, (byUser.get(u) || 0) + bytes(g));
  }
  return {
    month: total(a.month),
    day: total(a.day),
    credentials: [...byUser].map(([username, egress]) => ({ username, egress })).sort((x, y) => y.egress - x.egress),
  };
}

function bytes(g) {
  const n = Number(g && g.sum && g.sum.egressBytes);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

/** 印がこれより古ければ配らない（見張りが止まった＝天井が効いているか分からない。決定 A） */
export const STALE_MS = 30 * 60 * 1000;

/** 入口の判定: KV の印 → { serve, reason }。reason は画面に出す 'month' | 'day' だけ（印が無い・古いときは null）。 */
export function gate(mark, now) {
  if (!mark || typeof mark.at !== 'number' || !(now - mark.at < STALE_MS)) return { serve: false, reason: null };
  if (mark.serve === true) return { serve: true, reason: null };
  return { serve: false, reason: mark.reason === 'month' || mark.reason === 'day' ? mark.reason : null };
}
