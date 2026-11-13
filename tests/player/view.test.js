import { test } from 'node:test';
import assert from 'node:assert/strict';
import { makeView, viewChanged, cleanView, chipState, nextScreen, bannerFor, videosOn, pickVideo, mustStopFor, videoName, clampSplit, splitAt, SPLIT_DEFAULT, SPLIT_MIN, SPLIT_MAX, clampNotesSize, NOTES_DEFAULT, NOTES_MIN, NOTES_MAX } from '../../player/js/view.js';
import { resolveVideos, validateWork } from '../../player/js/work.js';
import { createSession, onHello, approve, reject, onView, knownToken } from '../../player/js/protocol.js';

const work = {
  format: 'digital-kamishibai/work', version: 1, title: 'T', language: 'en',
  slides: [1, 2, 3].map((n) => ({ number: n, title: `S${n}`, picture: `pictures/0${n}.jpg`, notes: `SECRET NOTES ${n}`, cues: [] })),
};
const pictures = new Map([1, 2, 3].map((n) => [n, { mime: 'image/jpeg', size: 100 * n, key: `pictures/0${n}.jpg` }]));

const base = { slide: 3, picture: true, video: null, waiting: false, sound: 'on', recv: { got: 10, all: 10 } };

// ---------- 聞き手の報告 ----------

test('報告: 絵・自分の動画・その場で流す・準備中を見分ける', () => {
  assert.equal(makeView(base).show, 'picture');
  assert.equal(makeView({ ...base, video: { local: true, playing: true } }).show, 'video');
  assert.equal(makeView({ ...base, video: { stream: true, playing: true } }).show, 'stream');
  assert.equal(makeView({ ...base, waiting: true }).show, 'waiting');      // 動画がまだ出せない
  assert.equal(makeView({ ...base, picture: false }).show, 'waiting');     // 今の枚の絵がまだ届いていない
  assert.equal(makeView({ ...base, video: { local: true, playing: false } }).playing, false);
  assert.equal('playing' in makeView(base), false);
});

test('報告: 中身は状態の名前と数だけ（絵・台本・パスを持たない）', () => {
  const v = makeView({ ...base, picture: 'blob:xyz', extra: 'SECRET', sound: 'loud', recv: { got: 50, all: 20 } });
  assert.deepEqual(Object.keys(v).sort(), ['mic', 'recv', 'show', 'slide', 'sound', 't']);
  assert.equal(v.mic, 'none');
  assert.equal(v.sound, 'none');           // 知らない名前は持ち込まない
  assert.deepEqual(v.recv, { got: 20, all: 20 });
  assert.ok(!JSON.stringify(v).includes('blob:'));
});

test('報告: 画面が変わったときだけ送る', () => {
  const a = makeView(base);
  assert.equal(viewChanged(null, a), true);
  assert.equal(viewChanged(a, makeView(base)), false);
  assert.equal(viewChanged(a, makeView({ ...base, slide: 4 })), true);
  assert.equal(viewChanged(a, makeView({ ...base, sound: 'tap' })), true);
  assert.equal(viewChanged(a, makeView({ ...base, recv: { got: 5, all: 10 } })), true);
});

test('語り手は報告を知っている項目だけで作り直し、形の違うものは捨てる', () => {
  assert.equal(cleanView(null), null);
  assert.equal(cleanView({ t: 'view', slide: 0, show: 'picture', sound: 'on' }), null);
  assert.equal(cleanView({ t: 'view', slide: 2, show: 'screenshot', sound: 'on' }), null);
  assert.equal(cleanView({ t: 'view', slide: 2, show: 'picture', sound: 'max' }), null);
  assert.equal(cleanView({ t: 'view', slide: '2', show: 'picture', sound: 'on' }), null);
  const v = cleanView({ t: 'view', slide: 2, show: 'picture', sound: 'on', image: 'data:...', recv: { got: -1, all: 'x' } });
  assert.deepEqual(v, { slide: 2, show: 'picture', sound: 'on', mic: 'none', recv: { got: 0, all: 0 } });
  assert.equal(cleanView({ t: 'view', slide: 2, show: 'picture', sound: 'on', mic: 'on' }).mic, 'on');
  assert.equal(cleanView({ t: 'view', slide: 2, show: 'picture', sound: 'on', mic: 'spy' }).mic, 'none');
});

// ---------- 承認していない端末の報告は捨てる（R7） ----------

test('承認していない端末・断った端末・知らない端末の報告は札に載らない', () => {
  const s = createSession(2);
  onHello(s, 'a', { name: 'A' });
  onHello(s, 'b', { name: 'B' });
  const msg = makeView(base);
  assert.equal(onView(s, 'a', msg), false);            // 承認待ち
  assert.equal(s.peers.get('a').view, undefined);
  reject(s, 'b');
  assert.equal(onView(s, 'b', msg), false);            // 断った
  assert.equal(s.peers.get('b').view, undefined);
  assert.equal(onView(s, 'zzz', msg), false);          // 名乗っていない
  assert.equal(s.peers.has('zzz'), false);
  approve(s, 'a', work, pictures);
  assert.equal(onView(s, 'a', msg), true);
  assert.deepEqual(s.peers.get('a').view, { slide: 3, show: 'picture', sound: 'on', mic: 'none', recv: { got: 10, all: 10 } });
  assert.equal(onView(s, 'a', { t: 'view', slide: 'x' }), false); // 壊れた報告で前の札を消さない
  assert.equal(s.peers.get('a').view.slide, 3);
});

// ---------- 札の判定（食い違い・タップ待ち） ----------

const view = (o) => cleanView(makeView({ ...base, ...o }));

test('札: 語り手と同じ枚・絵・音が出せる端末は ok', () => {
  assert.equal(chipState(view({}), { slide: 3, video: false }).level, 'ok');
});

test('札: 語り手の枚と食い違う端末は warn', () => {
  const c = chipState(view({ slide: 2 }), { slide: 3, video: false });
  assert.equal(c.level, 'warn');
  assert.equal(c.slide, true);
  assert.equal(c.show, false);   // 枚が違うときは、絵か動画かは判定しない（枚の食い違いだけを出す）
});

test('札: 音がタップ待ちの端末は warn', () => {
  const c = chipState(view({ sound: 'tap' }), { slide: 3, video: false });
  assert.equal(c.level, 'warn');
  assert.equal(c.sound, true);
  assert.equal(chipState(view({ sound: 'none' }), { slide: 3, video: false }).level, 'ok'); // 鳴らせない作品・端末は責めない
});

test('札: 語り手が動画を始めたのに絵・準備中のままの端末は warn。自分の動画もその場で流すも ok', () => {
  const ex = { slide: 3, video: true };
  assert.equal(chipState(view({}), ex).show, true);
  assert.equal(chipState(view({ waiting: true }), ex).level, 'warn');
  assert.equal(chipState(view({ video: { local: true, playing: true } }), ex).level, 'ok');
  assert.equal(chipState(view({ video: { stream: true, playing: true } }), ex).level, 'ok');
  // 動画が止まったのに、まだ動画を出している端末
  assert.equal(chipState(view({ video: { local: true } }), { slide: 3, video: false }).show, true);
});

test('札: 受け取り中かどうか・報告の無い端末は unknown', () => {
  assert.equal(chipState(view({ recv: { got: 120, all: 270 } }), { slide: 3, video: false }).receiving, true);
  assert.equal(chipState(view({}), { slide: 3, video: false }).receiving, false);
  assert.equal(chipState(view({ recv: { got: 0, all: 0 } }), { slide: 3, video: false }).receiving, false);
  assert.equal(chipState(undefined, { slide: 3, video: false }).level, 'unknown');
});

// ---------- 画面の切り替え（U1） ----------

test('画面: 作品を読んだら準備 → 受付。足りない素材があれば準備に残る', () => {
  assert.equal(nextScreen('prep', { type: 'loaded', missing: 0 }, { hasWork: true }), 'room');
  assert.equal(nextScreen('prep', { type: 'loaded', missing: 2 }, { hasWork: true }), 'prep');
  // 素材フォルダを選び直して揃ったら受付へ
  assert.equal(nextScreen('prep', { type: 'loaded', missing: 0 }, { hasWork: true }), 'room');
});

test('画面: 受付・上演の途中で読み直しても、勝手に画面を移さない', () => {
  assert.equal(nextScreen('room', { type: 'loaded', missing: 0 }, { hasWork: true }), 'room');
  assert.equal(nextScreen('show', { type: 'loaded', missing: 0 }, { hasWork: true }), 'show');
});

test('画面: 開演を押したら上演へ（受付からでも）', () => {
  assert.equal(nextScreen('room', { type: 'started' }, { hasWork: true }), 'show');
  assert.equal(nextScreen('show', { type: 'started' }, { hasWork: true }), 'show');
});

test('画面: 上の帯でいつでも戻れる。作品を読むまでは準備から動かない', () => {
  assert.equal(nextScreen('show', { type: 'tab', to: 'room' }, { hasWork: true }), 'room');
  assert.equal(nextScreen('room', { type: 'tab', to: 'prep' }, { hasWork: true }), 'prep');
  assert.equal(nextScreen('room', { type: 'tab', to: 'show' }, { hasWork: true }), 'show');
  assert.equal(nextScreen('prep', { type: 'tab', to: 'room' }, { hasWork: false }), 'prep');
  assert.equal(nextScreen('prep', { type: 'tab', to: 'nowhere' }, { hasWork: true }), 'prep');
  assert.equal(nextScreen('bogus', { type: 'nothing' }), 'prep');
});

// ---------- 上演中の承認の知らせの帯（U5） ----------

test('帯: 上演の画面にいるときだけ、新しい端末を出す', () => {
  const s = createSession(2);
  onHello(s, 'a', { name: 'A' });
  assert.deepEqual(bannerFor(s.peers, 'show').map((p) => p.id), ['a']);
  assert.deepEqual(bannerFor(s.peers, 'room'), []);   // 受付の画面には一覧がある
  approve(s, 'a', work, pictures);
  assert.deepEqual(bannerFor(s.peers, 'show'), []);
});

test('帯: 入り直し（合い札）の端末は帯に出ない——語り手と同じ順で承認すると、帯は空のまま', () => {
  const s = createSession(1);
  const token = 'f'.repeat(32);
  onHello(s, 'a', { name: 'A', token });
  approve(s, 'a', work, pictures);
  // タブを閉じて開き直した（新しい peer ID・同じ合い札）。narrator.js と同じ手順: 名乗り → 合い札が合えば承認
  onHello(s, 'a2', { name: 'A', token });
  assert.equal(knownToken(s, token), true);
  approve(s, 'a2', work, pictures);
  assert.deepEqual(bannerFor(s.peers, 'show'), []);
  // 合い札の無い新しい端末は帯に出る
  onHello(s, 'c', { name: 'C', token: 'e'.repeat(32) });
  assert.equal(knownToken(s, 'e'.repeat(32)), false);
  assert.deepEqual(bannerFor(s.peers, 'show').map((p) => p.id), ['c']);
});

// ---------- 1枚に動画が複数ある枚（決定 B・W1〜W3） ----------

const vids = [
  { id: 'a', n: 13, key: 'videos/s13_v1_redbull.mp4' },
  { id: 'b', n: 14, key: 'videos/s14_v2_freeman.mp4' },
  { id: 'c', n: 14, key: 'videos/s14_v3_ws_game5.mp4' },
];

test('その枚の動画の一覧は台本に書いた順。動画の無い枚は空', () => {
  assert.deepEqual(videosOn(vids, 14).map((v) => v.id), ['b', 'c']);
  assert.deepEqual(videosOn(vids, 13).map((v) => v.id), ['a']);
  assert.deepEqual(videosOn(vids, 1), []);
});

test('枠に出す1本: 選んだもの。選んでいない・その枚に無いものを選んでいたら1本目', () => {
  const list = videosOn(vids, 14);
  assert.equal(pickVideo(list, null).id, 'b');
  assert.equal(pickVideo(list, 'c').id, 'c');
  assert.equal(pickVideo(list, 'a').id, 'b'); // 前の枚で選んだもの
  assert.equal(pickVideo([], 'c'), null);
});

test('切り替え: 流している（一時停止中も含む）別の動画があれば止める。同じ1本・何も流していなければ止めない', () => {
  assert.equal(mustStopFor(vids[2], 'b'), true);
  assert.equal(mustStopFor(vids[1], 'b'), false);
  assert.equal(mustStopFor(vids[2], null), false);
  assert.equal(mustStopFor(null, 'b'), true);
});

test('切り替えのボタンの名前はファイル名だけ（パス・種類を落とし、長いものは切る）', () => {
  assert.equal(videoName('videos/s14_v2_freeman.mp4'), 's14_v2_freeman');
  assert.equal(videoName('videos/' + 'x'.repeat(40) + '.mp4', 10), 'xxxxxxxxx…');
  assert.equal(videoName(''), '');
});

test('作品の検査は1枚に動画が何本あっても通し、素材の一覧は台本の順に全部を並べる（2本目を落とさない）', () => {
  const w = {
    format: 'digital-kamishibai/work', version: 1, title: 'T', language: 'en',
    slides: [
      { number: 1, title: 'a', picture: 'pictures/01.jpg', notes: '', cues: [] },
      { number: 2, title: 'b', picture: null, notes: '', cues: [{ type: 'video', file: 'videos/v2.mp4' }, { type: 'video', file: 'videos/v1.mp4' }, { type: 'video', file: 'videos/v3.mp4' }] },
    ],
  };
  const { work, errors } = validateWork(w);
  assert.deepEqual(errors, []);
  const files = new Map(['videos/v1.mp4', 'videos/v2.mp4', 'videos/v3.mp4'].map((k) => [k, { size: 10, name: k }]));
  const r = resolveVideos(work, [files]);
  assert.deepEqual(r.videos.map((v) => [v.n, v.key]), [[2, 'videos/v2.mp4'], [2, 'videos/v1.mp4'], [2, 'videos/v3.mp4']]);
});

// ---------- 上演の画面の境目（U8） ----------

test('境目の割合は 30〜65% に収め、数でなければ既定（覚えた値が壊れていても既定で動く）', () => {
  assert.equal(clampSplit(50), 50);
  assert.equal(clampSplit('48.26'), 48.3);
  assert.equal(clampSplit(10), SPLIT_MIN);
  assert.equal(clampSplit(90), SPLIT_MAX);
  for (const bad of [null, undefined, '', 'abc', NaN, Infinity]) assert.equal(clampSplit(bad), SPLIT_DEFAULT, String(bad));
});

test('ドラッグした位置から割合を出す', () => {
  assert.equal(splitAt(500, 100, 1000), 40);
  assert.equal(splitAt(100, 100, 1000), SPLIT_MIN);
  assert.equal(splitAt(1100, 100, 1000), SPLIT_MAX);
  assert.equal(splitAt(500, 100, 0), SPLIT_DEFAULT);
});

// ---------- 台本の字の大きさ ----------

test('台本の字の大きさは 1〜2.6rem に収め、数でなければ既定（覚えた値が壊れていても既定で動く）', () => {
  assert.equal(clampNotesSize(1.6), 1.6);
  assert.equal(clampNotesSize('1.6000000001'), 1.6);   // 0.2 を足し続けた誤差を丸める
  assert.equal(clampNotesSize(0.4), NOTES_MIN);
  assert.equal(clampNotesSize(9), NOTES_MAX);
  for (const bad of [null, undefined, '', 'abc', NaN, Infinity]) assert.equal(clampNotesSize(bad), NOTES_DEFAULT, String(bad));
});
