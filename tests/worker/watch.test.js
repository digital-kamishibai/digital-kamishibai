import { test } from 'node:test';
import assert from 'node:assert/strict';
import { watch, MARK, TTL } from '../../src/watch.js';
import worker from '../../src/worker.js';

// KV の代わり（get の 'json'・put の expirationTtl だけ）
function fakeKV(init = {}) {
  const m = new Map(Object.entries(init));
  const ttl = new Map();
  return {
    m, ttl,
    async get(k, type) { const v = m.get(k); if (v === undefined) return null; return type === 'json' ? JSON.parse(v) : v; },
    async put(k, v, opt) { m.set(k, v); if (opt && opt.expirationTtl) ttl.set(k, opt.expirationTtl); },
  };
}

const usage = (month, day, credentials) => ({ data: { viewer: { accounts: [{ month: [{ sum: { egressBytes: month } }], day: [{ sum: { egressBytes: day } }],
  credentials: credentials.map(([username, egressBytes]) => ({ dimensions: { username }, sum: { egressBytes } })) }] } }, errors: null });

// 外向きの通信の代わり。呼ばれた URL を残す
function fakeFetch(graphql, { revokeStatus = 204 } = {}) {
  const calls = [];
  const f = async (url, init) => {
    calls.push({ url, init });
    if (url.endsWith('/graphql')) return new Response(JSON.stringify(graphql), { status: 200 });
    if (url.includes('/revoke')) return new Response(null, { status: revokeStatus });
    throw new Error(`unexpected ${url}`);
  };
  f.calls = calls;
  return f;
}

const baseEnv = (kv) => ({ TURN_KEY_ID: 'key1', TURN_KEY_API_TOKEN: 'tok', CF_ANALYTICS_TOKEN: 'ana', CF_ACCOUNT_ID: 'acc', TURN_GUARD: kv,
  TURN_CAP_CREDENTIAL_GB: '0.000001', TURN_CAP_MONTH_GB: '0.00001', TURN_DAY_SHARE: '0.5' }); // 認証情報 1000・月 10000・日 5000 バイト
const NOW = Date.parse('2026-11-02T10:00:00Z');

test('見張り: 鍵が無い箱（開発用）では何もしない', async () => {
  const f = fakeFetch(usage(0, 0, []));
  assert.deepEqual(await watch({}, NOW, f), { skipped: 'no-turn-key' });
  assert.equal(f.calls.length, 0);
});

test('見張り: 照会のトークンか KV が無ければ印を付けない（入口は配らないまま）', async () => {
  const kv = fakeKV();
  const env = { ...baseEnv(kv), CF_ANALYTICS_TOKEN: '' };
  const err = console.error; console.error = () => {};
  try { assert.deepEqual(await watch(env, NOW, fakeFetch(usage(0, 0, []))), { skipped: 'no-guard-config' }); } finally { console.error = err; }
  assert.equal(kv.m.size, 0);
});

test('見張り: 照会 → 印（配る）→ 天井を超えた認証情報だけ取り消し、4時間の印', async () => {
  const kv = fakeKV();
  const f = fakeFetch(usage(3000, 3000, [['big', 1001], ['ok', 1000]]));
  const r = await watch(baseEnv(kv), NOW, f);
  assert.deepEqual(r, { serve: true, reason: null, revoked: 1, pending: 0 });
  const mark = JSON.parse(kv.m.get(MARK));
  assert.equal(mark.serve, true);
  assert.equal(mark.at, NOW);
  const q = JSON.parse(f.calls[0].init.body);
  assert.deepEqual(q.variables, { accountTag: 'acc', keyId: 'key1', monthStart: '2026-11-01', today: '2026-11-02', yesterday: '2026-11-01' });
  assert.equal(f.calls[0].init.headers.Authorization, 'Bearer ana');
  assert.equal(f.calls[1].url, 'https://rtc.live.cloudflare.com/v1/turn/keys/key1/credentials/big/revoke');
  assert.equal(f.calls[1].init.method, 'POST');
  assert.equal(f.calls[1].init.headers.Authorization, 'Bearer tok');
  assert.equal(kv.ttl.get('revoked:big'), TTL);
  assert.equal(TTL, 4 * 60 * 60);
});

test('見張り: 取り消し済みは2度取り消さない', async () => {
  const kv = fakeKV({ 'revoked:big': '1' });
  const f = fakeFetch(usage(3000, 3000, [['big', 5000]]));
  const r = await watch(baseEnv(kv), NOW, f);
  assert.equal(r.revoked, 0);
  assert.equal(f.calls.length, 1); // 照会だけ
});

test('見張り: 月を超えたら配らない印・使われた認証情報を1回40件まで取り消し、残りは次の回へ', async () => {
  const kv = fakeKV();
  const many = Array.from({ length: 45 }, (_, i) => [`u${i}`, 10]);
  const f = fakeFetch(usage(10001, 10, many));
  const r = await watch(baseEnv(kv), NOW, f);
  assert.deepEqual(r, { serve: false, reason: 'month', revoked: 40, pending: 5 });
  assert.equal(f.calls.length, 41); // 照会1＋取り消し40（無料プランの50回に収まる）
  assert.deepEqual(JSON.parse(kv.m.get(MARK)).reason, 'month');
  const f2 = fakeFetch(usage(10001, 10, many));
  const r2 = await watch(baseEnv(kv), NOW + 300_000, f2);
  assert.deepEqual(r2, { serve: false, reason: 'month', revoked: 5, pending: 0 });
});

test('見張り: 1日を超えたら配らない印（理由 day）', async () => {
  const kv = fakeKV();
  await watch(baseEnv(kv), NOW, fakeFetch(usage(6000, 5001, [])));
  assert.deepEqual(JSON.parse(kv.m.get(MARK)), { ...JSON.parse(kv.m.get(MARK)), serve: false, reason: 'day' });
});

test('見張り: 照会に失敗したら投げて、印を新しくしない（30分で入口が自分で止まる）', async () => {
  const kv = fakeKV({ [MARK]: JSON.stringify({ serve: true, at: NOW - 60_000 }) });
  const f = fakeFetch({ data: null, errors: [{ message: 'authentication error' }] });
  await assert.rejects(watch(baseEnv(kv), NOW, f), /authentication error/);
  assert.equal(JSON.parse(kv.m.get(MARK)).at, NOW - 60_000);
  const bad = async () => new Response('', { status: 500 });
  await assert.rejects(watch(baseEnv(kv), NOW, bad), /graphql 500/);
});

test('見張り: 取り消しに失敗したら印を付けず、次の回にもう一度', async () => {
  const kv = fakeKV();
  const err = console.error; console.error = () => {};
  try {
    const r = await watch(baseEnv(kv), NOW, fakeFetch(usage(10, 10, [['big', 5000]]), { revokeStatus: 500 }));
    assert.deepEqual(r, { serve: true, reason: null, revoked: 0, pending: 1 });
  } finally { console.error = err; }
  assert.equal(kv.m.has('revoked:big'), false);
});

// ---------- 入口（/api/ice） ----------

const iceReq = () => new Request('https://room.example/api/ice', { headers: { 'Sec-Fetch-Site': 'same-origin' } });

async function callIce(env, turnBody) {
  const real = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url) => { calls.push(url); return new Response(JSON.stringify(turnBody), { status: 201 }); };
  try {
    const res = await worker.fetch(iceReq(), env);
    return { body: await res.json(), calls };
  } finally { globalThis.fetch = real; }
}

const turnBody = { iceServers: [{ urls: ['stun:stun.cloudflare.com:3478'] }, { urls: ['turn:turn.cloudflare.com:3478?transport=udp'], username: 'u', credential: 'c' }] };

test('入口: 鍵が無ければ STUN だけ（印は見ない）', async () => {
  const { body, calls } = await callIce({}, turnBody);
  assert.deepEqual(body, { iceServers: [{ urls: ['stun:stun.cloudflare.com:3478'] }], turn: false });
  assert.equal(calls.length, 0);
});

test('入口: 新しい「配る」の印なら中継を配る', async () => {
  const kv = fakeKV({ [MARK]: JSON.stringify({ serve: true, at: Date.now() }) });
  const { body, calls } = await callIce(baseEnv(kv), turnBody);
  assert.equal(body.turn, true);
  assert.equal(calls.length, 1);
});

test('入口: 「配らない」の印なら STUN だけと理由（month／day）。認証情報は作らない', async () => {
  for (const reason of ['month', 'day']) {
    const kv = fakeKV({ [MARK]: JSON.stringify({ serve: false, reason, at: Date.now() }) });
    const { body, calls } = await callIce(baseEnv(kv), turnBody);
    assert.deepEqual(body, { iceServers: [{ urls: ['stun:stun.cloudflare.com:3478'] }], turn: false, reason });
    assert.equal(calls.length, 0);
  }
});

test('入口: 印が無い・30分以上古い・KV が無いなら配らない（理由なし）', async () => {
  const stale = fakeKV({ [MARK]: JSON.stringify({ serve: true, at: Date.now() - 31 * 60 * 1000 }) });
  for (const env of [baseEnv(fakeKV()), baseEnv(stale), { ...baseEnv(null), TURN_GUARD: undefined }]) {
    const { body, calls } = await callIce(env, turnBody);
    assert.deepEqual(body, { iceServers: [{ urls: ['stun:stun.cloudflare.com:3478'] }], turn: false });
    assert.equal(calls.length, 0);
  }
});

test('Cron の入口は見張りを waitUntil に渡す', async () => {
  let p = null;
  await worker.scheduled({}, {}, { waitUntil: (x) => { p = x; } });
  const log = console.log; console.log = () => {};
  try { await p; } finally { console.log = log; }
  assert.ok(p instanceof Promise);
});
