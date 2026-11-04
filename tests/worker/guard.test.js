import { test } from 'node:test';
import assert from 'node:assert/strict';
import { monthCapBytes, readCaps, readDonation, donationKey, DONATION_MAX_USD, decide, pickRevokes, utcRange, usageVariables, readUsage, gate, STALE_MS, USAGE_QUERY } from '../../src/guard.js';

const GB = 1e9;
const near = (a, b) => assert.ok(Math.abs(a - b) < 1, `${a} ≈ ${b}`);

test('月の枠: 寄付なしで 1,000GB ＋ 1,000ドル÷12÷0.05ドル ≈ 2,667GB', () => {
  near(monthCapBytes(), (1000 + 1000 / 12 / 0.05) * GB);
  assert.ok(Math.round(monthCapBytes() / GB) === 2667);
});

test('月の枠: 前の月の寄付 50ドルで 1,000GB 増える', () => {
  near(monthCapBytes({ donationUsd: 50 }) - monthCapBytes(), 1000 * GB);
});

test('天井の既定値: 認証情報ごと 20GB・1日は月の10分の1', () => {
  const c = readCaps({});
  assert.equal(c.credential, 20 * GB);
  near(c.month, monthCapBytes());
  near(c.day, monthCapBytes() / 10);
});

test('天井は設定の値で変えられる（試験用で小さく）・寄付は設定から入らない', () => {
  const c = readCaps({ TURN_CAP_CREDENTIAL_GB: '0.001', TURN_CAP_MONTH_GB: '0.05', TURN_DAY_SHARE: '0.4' });
  assert.equal(c.credential, 1e6);
  assert.equal(c.month, 5e7);
  near(c.day, 2e7);
  near(readCaps({ TURN_FREE_GB: '0', TURN_YEARLY_USD: '120', TURN_USD_PER_GB: '0.1' }).month, 100 * GB);
  near(readCaps({ TURN_DONATION_USD: '50' }).month, monthCapBytes());
});

test('寄付額のキーは UTC の前の月（年をまたぐ1月・月の境目）', () => {
  assert.equal(donationKey(Date.parse('2026-12-15T00:00:00Z')), 'donation:2026-11');
  assert.equal(donationKey(Date.parse('2027-01-01T00:00:00Z')), 'donation:2026-12');
  assert.equal(donationKey(Date.parse('2026-11-30T23:59:59Z')), 'donation:2026-10');
  assert.equal(donationKey(Date.parse('2026-03-31T12:00:00Z')), 'donation:2026-02');
});

test('寄付額: 無い・数でない・負・上限超えは 0（枠を広げない側）', () => {
  assert.equal(readDonation(null), 0);
  assert.equal(readDonation(''), 0);
  assert.equal(readDonation('abc'), 0);
  assert.equal(readDonation('-5'), 0);
  assert.equal(readDonation(String(DONATION_MAX_USD + 0.01)), 0);
  assert.equal(readDonation('2500'), 0);
  assert.equal(readDonation('25'), 25);
  assert.equal(readDonation('12.5'), 12.5);
  assert.equal(readDonation(String(DONATION_MAX_USD)), DONATION_MAX_USD);
  assert.equal(DONATION_MAX_USD, 1000);
});

test('寄付額は月の枠に足される・上限超えは足されない・月の枠を直に決めたときは効かない', () => {
  near(readCaps({}, 50).month - readCaps({}).month, 1000 * GB);
  near(readCaps({}, '50').month - readCaps({}).month, 1000 * GB);
  near(readCaps({}, 2500).month, readCaps({}).month);
  near(readCaps({ TURN_CAP_MONTH_GB: '0.05' }, 50).month, 5e7);
});

test('読めない設定の値は既定値に戻す（空・数でない・負）', () => {
  const c = readCaps({ TURN_CAP_CREDENTIAL_GB: 'abc', TURN_CAP_MONTH_GB: '', TURN_DAY_SHARE: '-1' });
  assert.equal(c.credential, 20 * GB);
  near(c.month, monthCapBytes());
  near(c.day, monthCapBytes() / 10);
});

const caps = { credential: 100, month: 10000, day: 1000 };
const creds = [{ username: 'a', egress: 101 }, { username: 'b', egress: 100 }, { username: 'c', egress: 0 }];

test('判定: どれも超えていなければ配る。ちょうどは超えていない', () => {
  assert.deepEqual(decide({ month: 10000, day: 1000, credentials: [{ username: 'b', egress: 100 }] }, caps), { serve: true, reason: null, revoke: [] });
});

test('判定: 認証情報ごとの天井を超えたものだけ取り消し、配るのは続ける', () => {
  assert.deepEqual(decide({ month: 500, day: 500, credentials: creds }, caps), { serve: true, reason: null, revoke: ['a'] });
});

test('判定: 1日を超えたら配らない（理由 day）。出回っているものは天井を超えたものだけ取り消す', () => {
  assert.deepEqual(decide({ month: 5000, day: 1001, credentials: creds }, caps), { serve: false, reason: 'day', revoke: ['a'] });
});

test('判定: 月を超えたら配らない（理由 month）。使われた認証情報はみな取り消す・日より月が先', () => {
  assert.deepEqual(decide({ month: 10001, day: 5000, credentials: creds }, caps), { serve: false, reason: 'month', revoke: ['a', 'b'] });
});

test('取り消しは1回40件まで・取り消し済みと重複は飛ばす', () => {
  const list = Array.from({ length: 50 }, (_, i) => `u${i}`);
  const out = pickRevokes(['u0', ...list], new Set(['u1', 'u2']));
  assert.equal(out.length, 40);
  assert.deepEqual(out.slice(0, 3), ['u0', 'u3', 'u4']);
  assert.deepEqual(pickRevokes(['x'], new Set(['x'])), []);
});

test('日付の区切りは UTC（日本時間の朝8時はまだ前の日）', () => {
  assert.deepEqual(utcRange(Date.parse('2026-12-01T08:00:00+09:00')), { monthStart: '2026-11-01', today: '2026-11-30', yesterday: '2026-11-29' });
  assert.deepEqual(utcRange(Date.parse('2027-01-01T00:00:00Z')), { monthStart: '2027-01-01', today: '2027-01-01', yesterday: '2026-12-31' });
  assert.deepEqual(usageVariables({ accountTag: 'acc', keyId: 'key', now: Date.parse('2026-03-01T00:10:00Z') }),
    { accountTag: 'acc', keyId: 'key', monthStart: '2026-03-01', today: '2026-03-01', yesterday: '2026-02-28' });
});

test('照会は公式の形（callsTurnUsageAdaptiveGroups・sum.egressBytes・date_geq/date_leq）で、認証情報ごとは自分の鍵に絞る', () => {
  assert.match(USAGE_QUERY, /accounts\(filter: \{ accountTag: \$accountTag \}\)/);
  assert.equal(USAGE_QUERY.match(/callsTurnUsageAdaptiveGroups/g).length, 3);
  assert.match(USAGE_QUERY, /keyId: \$keyId/);
  assert.match(USAGE_QUERY, /dimensions \{ username \}/);
  assert.match(USAGE_QUERY, /orderBy: \[sum_egressBytes_DESC\]/);
});

// 公式の例（TURN analytics の Example response）と同じ形の返事。照会の別名（month・day・credentials）で組が分かれる
const sample = {
  data: {
    viewer: {
      accounts: [
        {
          month: [{ sum: { egressBytes: 160040068147 } }],
          day: [{ sum: { egressBytes: 207314144 } }],
          credentials: [
            { dimensions: { username: 'bc91b63e' }, sum: { egressBytes: 162641324 } },
            { dimensions: { username: 'aa00ff11' }, sum: { egressBytes: 44683820 } },
          ],
        },
      ],
    },
  },
  errors: null,
};

test('GraphQL の返事を読む: 月・日の合計と認証情報ごと（多い順）', () => {
  assert.deepEqual(readUsage(sample), {
    month: 160040068147,
    day: 207314144,
    credentials: [{ username: 'bc91b63e', egress: 162641324 }, { username: 'aa00ff11', egress: 44683820 }],
  });
});

test('GraphQL の返事: 組が空なら 0・同じ認証情報が分かれていたら足す・username の無い組は飛ばす', () => {
  const body = { data: { viewer: { accounts: [{ month: [], day: [], credentials: [
    { dimensions: { username: 'x' }, sum: { egressBytes: 5 } },
    { dimensions: { username: 'y' }, sum: { egressBytes: 7 } },
    { dimensions: { username: 'x' }, sum: { egressBytes: 4 } },
    { dimensions: {}, sum: { egressBytes: 99 } },
  ] }] } } };
  assert.deepEqual(readUsage(body), { month: 0, day: 0, credentials: [{ username: 'x', egress: 9 }, { username: 'y', egress: 7 }] });
});

test('GraphQL の返事が読めなければ投げる（errors・アカウントが無い・形が違う）', () => {
  assert.throws(() => readUsage({ data: null, errors: [{ message: 'not authorized for that account' }] }), /not authorized/);
  assert.throws(() => readUsage({ data: { viewer: { accounts: [] } }, errors: null }), /account/);
  assert.throws(() => readUsage({ data: { viewer: { accounts: [{ month: [] }] } } }), /no day/);
  assert.throws(() => readUsage(null), /empty/);
});

test('入口の判定: 新しい印なら印のとおり', () => {
  const now = 1_000_000_000;
  assert.deepEqual(gate({ serve: true, at: now - 60_000 }, now), { serve: true, reason: null });
  assert.deepEqual(gate({ serve: false, reason: 'month', at: now }, now), { serve: false, reason: 'month' });
  assert.deepEqual(gate({ serve: false, reason: 'day', at: now }, now), { serve: false, reason: 'day' });
  assert.deepEqual(gate({ serve: false, reason: 'other', at: now }, now), { serve: false, reason: null });
});

test('入口の判定: 印が無い・30分以上古いなら配らない（理由は出さない）', () => {
  const now = 1_000_000_000;
  assert.deepEqual(gate(null, now), { serve: false, reason: null });
  assert.deepEqual(gate({ serve: true }, now), { serve: false, reason: null });
  assert.deepEqual(gate({ serve: true, at: now - STALE_MS + 1 }, now), { serve: true, reason: null });
  assert.deepEqual(gate({ serve: true, at: now - STALE_MS }, now), { serve: false, reason: null });
  assert.equal(STALE_MS, 30 * 60 * 1000);
});
