import { test } from 'node:test';
import assert from 'node:assert/strict';
import { summarizeIce, keepLast, looksBlocked, isAndroid, whyBlocked, routeOf, relayNote, forcedRelay } from '../../player/js/ice.js';

// 2026-10-24 の実機（有線の PC ↔ Android 17 の Pixel。Chrome にローカル ネットワーク権限が無かった）のダンプを縮めたもの
const blocked = new Map([
  ['L1', { type: 'local-candidate', candidateType: 'host', address: '192.168.1.99' }],
  ['L2', { type: 'local-candidate', candidateType: 'srflx', address: '203.0.113.7' }],
  ['L3', { type: 'local-candidate', candidateType: 'host', address: 'abcd.local' }],
  ['R1', { type: 'remote-candidate', candidateType: 'host', address: '192.168.1.61' }],
  ['P1', { type: 'candidate-pair', requestsSent: 31, responsesReceived: 0, requestsReceived: 0 }],
  ['P2', { type: 'candidate-pair', requestsSent: 33, responsesReceived: 0, requestsReceived: 0 }],
]);

test('確認の往復を数える（候補の数ではなく）', () => {
  const s = summarizeIce(blocked, 'checking');
  assert.equal(s.sent, 64);
  assert.equal(s.answered, 0);
  assert.equal(s.heard, 0);
  assert.equal(s.pairs, 2);
  assert.deepEqual(s.local, { host: 1, srflx: 1, mdns: 1 });
});

test('返事も受信も0なら「届いていない」と判定する', () => {
  assert.equal(looksBlocked(summarizeIce(blocked)), true);
});

test('送った数が少ないうちは判定しない（遅い回線で早まらない）', () => {
  const early = new Map([['P1', { type: 'candidate-pair', requestsSent: 12, responsesReceived: 0, requestsReceived: 0 }]]);
  assert.equal(looksBlocked(summarizeIce(early)), false);
});

test('返事か相手からの確認が1つでもあれば「届いていない」としない', () => {
  const answered = new Map([['P1', { type: 'candidate-pair', requestsSent: 40, responsesReceived: 1, requestsReceived: 0 }]]);
  const heard = new Map([['P1', { type: 'candidate-pair', requestsSent: 40, responsesReceived: 0, requestsReceived: 2 }]]);
  assert.equal(looksBlocked(summarizeIce(answered)), false);
  assert.equal(looksBlocked(summarizeIce(heard)), false);
});

test('失敗して統計が消えても、前回の数を残して状態だけ新しくする', () => {
  const before = summarizeIce(blocked, 'checking');
  const after = keepLast(before, summarizeIce(new Map(), 'failed'));
  assert.equal(after.state, 'failed');
  assert.equal(after.sent, 64);
  assert.equal(looksBlocked(after), true);
  // 最初から何も無ければ、空のまま
  assert.equal(keepLast(undefined, summarizeIce([], 'new')).pairs, 0);
});

test('getStats() の結果でなく普通の配列も読める', () => {
  assert.equal(summarizeIce([...blocked.values()]).sent, 64);
});

test('Android の判定は deviceKind() の名前で行う', () => {
  assert.equal(isAndroid('Android phone'), true);
  assert.equal(isAndroid('Android tablet'), true);
  assert.equal(isAndroid('Windows PC'), false);
  assert.equal(isAndroid(undefined), false);
});

// ---------- どこで止まっているか（whyBlocked） ----------

const withRelay = new Map([
  ...blocked,
  ['L4', { type: 'local-candidate', candidateType: 'relay', address: '198.51.100.9' }],
]);

test('中継が無いとき: Android なら権限、それ以外は同じネットワークを聞く（これまでの案内のまま）', () => {
  const s = summarizeIce(blocked);
  assert.equal(whyBlocked(s, { relay: false, android: true }), 'local-net');
  assert.equal(whyBlocked(s, { relay: false, android: false }), 'same-wifi');
  assert.equal(whyBlocked(s), 'same-wifi');
});

test('中継を配っているのに relay の候補が無い＝この端末のネットワークが中継を通さない', () => {
  assert.equal(whyBlocked(summarizeIce(blocked), { relay: true, android: false }), 'no-relay-here');
});

test('中継があるときは Android でも権限の案内を出さない（中継は家の中の通信を使わない）', () => {
  assert.equal(whyBlocked(summarizeIce(blocked), { relay: true, android: true }), 'no-relay-here');
  assert.equal(whyBlocked(summarizeIce(withRelay), { relay: true, android: true }), 'no-relay-there');
});

test('この端末は中継に出られるのに返事が無い＝相手側のネットワーク', () => {
  assert.equal(whyBlocked(summarizeIce(withRelay), { relay: true }), 'no-relay-there');
});

test('まだ判定できない・返事があるときは何も言わない', () => {
  const early = new Map([['P1', { type: 'candidate-pair', requestsSent: 12, responsesReceived: 0, requestsReceived: 0 }]]);
  const answered = new Map([['P1', { type: 'candidate-pair', requestsSent: 40, responsesReceived: 1, requestsReceived: 0 }]]);
  assert.equal(whyBlocked(summarizeIce(early), { relay: true }), null);
  assert.equal(whyBlocked(summarizeIce(answered), { relay: false, android: true }), null);
  assert.equal(whyBlocked(null), null);
});

// ---------- 直接か中継か（routeOf） ----------

const cand = (id, candidateType) => [id, { id, type: id.startsWith('L') ? 'local-candidate' : 'remote-candidate', candidateType }];

test('Chrome・Safari: transport の selectedCandidatePairId で選ばれた組を見る', () => {
  const direct = new Map([
    cand('L1', 'host'), cand('R1', 'srflx'), cand('L2', 'relay'), cand('R2', 'relay'),
    ['P1', { id: 'P1', type: 'candidate-pair', localCandidateId: 'L1', remoteCandidateId: 'R1', state: 'succeeded' }],
    ['P2', { id: 'P2', type: 'candidate-pair', localCandidateId: 'L2', remoteCandidateId: 'R2', state: 'succeeded', nominated: true }],
    ['T1', { id: 'T1', type: 'transport', selectedCandidatePairId: 'P1' }],
  ]);
  assert.equal(routeOf(direct), 'direct'); // 中継の組が並んでいても、選ばれていなければ直接
  direct.set('T1', { id: 'T1', type: 'transport', selectedCandidatePairId: 'P2' });
  assert.equal(routeOf(direct), 'relay');
});

test('どちらかの端が relay なら中継', () => {
  const half = new Map([
    cand('L1', 'srflx'), cand('R1', 'relay'),
    ['P1', { id: 'P1', type: 'candidate-pair', localCandidateId: 'L1', remoteCandidateId: 'R1' }],
    ['T1', { id: 'T1', type: 'transport', selectedCandidatePairId: 'P1' }],
  ]);
  assert.equal(routeOf(half), 'relay');
});

test('Firefox: transport が無く、組の selected で見る', () => {
  const ff = [
    { id: 'L1', type: 'local-candidate', candidateType: 'relay' },
    { id: 'R1', type: 'remote-candidate', candidateType: 'host' },
    { id: 'P1', type: 'candidate-pair', localCandidateId: 'L1', remoteCandidateId: 'R1', selected: true },
  ];
  assert.equal(routeOf(ff), 'relay');
});

test('選ばれた組が無い・候補が引けないときは null（札に何も出さない）', () => {
  assert.equal(routeOf(new Map()), null);
  assert.equal(routeOf(new Map([['P1', { id: 'P1', type: 'candidate-pair', state: 'in-progress' }]])), null);
  const dangling = new Map([
    ['P1', { id: 'P1', type: 'candidate-pair', localCandidateId: 'Lx', remoteCandidateId: 'Rx', selected: true }],
  ]);
  assert.equal(routeOf(dangling), null);
});

test('中継を止めている理由 → 案内の文の鍵（語り手と聞き手で別）。理由が無ければ案内しない', () => {
  assert.equal(relayNote('month'), 'relayMonth');
  assert.equal(relayNote('day'), 'relayDay');
  assert.equal(relayNote('month', 'listener'), 'relayMonthListener');
  assert.equal(relayNote('day', 'listener'), 'relayDayListener');
  assert.equal(relayNote(null), null);
  assert.equal(relayNote('stale'), null);
});

test('?relay を付けたページは中継だけを使う。中継を配っていなければ効かせない', () => {
  assert.deepEqual(forcedRelay('?relay', true), { iceTransportPolicy: 'relay' });
  assert.deepEqual(forcedRelay('?test&relay', true), { iceTransportPolicy: 'relay' });
  assert.deepEqual(forcedRelay('?relay', false), {});
  assert.deepEqual(forcedRelay('', true), {});
  assert.deepEqual(forcedRelay('?relayx', true), {});
});
