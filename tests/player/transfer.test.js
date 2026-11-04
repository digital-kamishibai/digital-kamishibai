import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  SEGMENT, WINDOW, SEND_HIGH, SIZE_LIMIT, FREE_MARGIN,
  storedBytes, sendable, planTransfers, mustWait, segmentReady, progress, fmtTime, PIC_LOW, picReady, nextPicture,
} from '../../player/js/transfer.js';

const MB = 1e6;
const v270 = { id: 'a', key: 'videos/ending.mp4', size: 270 * MB };

test('持っている分は、書けた区切りに切り詰める（区切りの途中は端末に無い）', () => {
  assert.equal(storedBytes(0, v270.size), 0);
  assert.equal(storedBytes(SEGMENT * 3 + 10, v270.size), SEGMENT * 3);
  assert.equal(storedBytes(v270.size, v270.size), v270.size); // 最後の端切れまで揃えば全部
  assert.equal(storedBytes(v270.size + 5, v270.size), v270.size);
  assert.equal(storedBytes(undefined, v270.size), 0);
});

test('配れない動画（MP4 でない・上限超え）は理由つきで「その場で流す」', () => {
  assert.equal(sendable(v270), null);
  assert.equal(sendable({ key: 'videos/x.mov', size: 1 }), 'not-mp4');
  assert.equal(sendable({ key: 'videos/x.mp4', size: SIZE_LIMIT + 1 }), 'too-big');
  const plan = planTransfers([{ id: 'b', key: 'v/x.mp4', size: 906 * MB }], { store: 'opfs', free: Infinity, items: [] });
  assert.deepEqual(plan, [{ id: 'b', mode: 'stream', from: 0, reason: 'too-big' }]);
});

test('保存できる端末には保存で送る。入り直したら続きから、受け取り済みなら送らない', () => {
  const have = { store: 'opfs', free: 10e9, items: [{ id: 'a', bytes: SEGMENT * 10 + 123 }] };
  assert.deepEqual(planTransfers([v270], have), [{ id: 'a', mode: 'stored', from: SEGMENT * 10, reason: null }]);
  const done = { store: 'idb', free: 0, items: [{ id: 'a', bytes: v270.size }] };
  assert.deepEqual(planTransfers([v270], done), [{ id: 'a', mode: 'stored', from: v270.size, reason: null }]);
});

test('保存できない・空き容量が足りない端末は「その場で流す」', () => {
  assert.equal(planTransfers([v270], { store: null, items: [] })[0].reason, 'no-store');
  assert.equal(planTransfers([v270], null)[0].reason, 'no-store');
  const tight = { store: 'opfs', free: v270.size + FREE_MARGIN - 1, items: [] };
  assert.equal(planTransfers([v270], tight)[0].reason, 'no-space');
  // 空き容量は動画を足していくごとに減る
  const two = [v270, { ...v270, id: 'c' }];
  const plan = planTransfers(two, { store: 'opfs', free: v270.size + FREE_MARGIN + 1, items: [] });
  assert.deepEqual(plan.map((p) => p.mode), ['stored', 'stream']);
});

test('送り手は、送り待ちが多いか、返事の来ていない分が窓を超えたら待つ', () => {
  assert.equal(mustWait(0, 0, 0), false);
  assert.equal(mustWait(SEND_HIGH + 1, 0, 0), true);
  assert.equal(mustWait(0, WINDOW, 0), true);
  assert.equal(mustWait(0, WINDOW - 1, 0), false);
});

test('受け手は1区切り溜まるか、最後の端切れで書く', () => {
  assert.equal(segmentReady(SEGMENT - 1, 0, 100 * MB), false);
  assert.equal(segmentReady(SEGMENT, 0, 100 * MB), true);
  assert.equal(segmentReady(10, 100 * MB - 10, 100 * MB), true);
});

test('受け取りの速さと残りの見込み', () => {
  const p = progress(100 * MB, 270 * MB, 0, 20_000);
  assert.equal(p.pct, 37);
  assert.equal(p.mbps, 5);
  assert.equal(p.eta, 34);
  // 続きから受け取った分は速さに数えない
  assert.equal(progress(150 * MB, 270 * MB, 0, 10_000, 100 * MB).mbps, 5);
  assert.equal(fmtTime(125), '2:05');
  assert.equal(fmtTime(null), '—');
});

// ---------- 絵の送り出し（2026-10-25 D1・D2） ----------

test('次の絵は、いまの枚 → その先（近い順）→ 前の枚（近い順）', () => {
  assert.equal(nextPicture(new Set([1, 2, 5, 6, 9]), 5), 5);
  assert.equal(nextPicture(new Set([1, 2, 6, 9]), 5), 6);
  assert.equal(nextPicture(new Set([1, 2]), 5), 2);       // 先が無ければ、近い前の枚
  assert.equal(nextPicture(new Set([3, 18, 1]), 18), 18);
  assert.equal(nextPicture(new Set(), 3), null);
  // 送る途中で語り手が先へ進んだら、選び直すと先の枚から
  const pending = new Set([2, 3, 4, 10, 11]);
  assert.equal(nextPicture(pending, 1), 2);
  assert.equal(nextPicture(pending, 10), 10);
});

test('次の絵は、送り待ちが小さくなってから（PeerJS の列が空・ブラウザの列が PIC_LOW 以下）', () => {
  assert.equal(picReady(0, 0), true);
  assert.equal(picReady(PIC_LOW, 0), true);
  assert.equal(picReady(PIC_LOW + 1, 0), false);
  assert.equal(picReady(0, 1), false);
  assert.equal(picReady(undefined, undefined), true);
});
