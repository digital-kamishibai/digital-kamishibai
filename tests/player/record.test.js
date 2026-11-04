import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  MIMES, pickMime, recordName, fitRect, stageSource, createClock, clockStart, clockSlide, clockRead, isPractice, recordable,
} from '../../player/js/record.js';
import { createSession, onHello, approve, reject, setRecording, goTo } from '../../player/js/protocol.js';

const work = {
  format: 'digital-kamishibai/work', version: 1, title: 'T', language: 'en',
  slides: [1, 2, 3].map((n) => ({ number: n, title: `S${n}`, picture: `pictures/0${n}.jpg`, notes: `SECRET NOTES ${n}`, cues: [] })),
};
const pictures = new Map([1, 2, 3].map((n) => [n, { mime: 'image/jpeg', size: 100 * n, key: `pictures/0${n}.jpg` }]));

// ---------- 録画中の合図（G4） ----------

test('録画中の合図は承認済みの端末にだけ届く（承認待ち・断った端末へは送らない）', () => {
  const s = createSession(3);
  for (const id of ['a', 'b', 'c']) onHello(s, id, { name: id });
  approve(s, 'a', work, pictures);
  reject(s, 'c');
  const out = setRecording(s, true);
  assert.deepEqual(out, [{ to: 'a', msg: { t: 'rec', on: true } }]);
  assert.equal(s.recording, true);
  assert.deepEqual(setRecording(s, false), [{ to: 'a', msg: { t: 'rec', on: false } }]);
  assert.equal(s.recording, false);
});

test('練習（受付を開いていない＝聞き手がいない）では、録画中の合図の送り先は無い', () => {
  const s = createSession(1);
  assert.deepEqual(setRecording(s, true), []);
  assert.equal(s.recording, true);
});

test('去った端末（受付から消えた端末）へは送らない', () => {
  const s = createSession(2);
  onHello(s, 'a', {}); approve(s, 'a', work, pictures);
  onHello(s, 'b', {}); approve(s, 'b', work, pictures);
  s.peers.delete('b'); // onGone と同じ
  assert.deepEqual(setRecording(s, true).map((o) => o.to), ['a']);
});

test('録画中に承認した端末（途中から入った・入り直した）には、絵より先に「録画中」を知らせる', () => {
  const s = createSession(2);
  setRecording(s, true);
  onHello(s, 'a', {});
  const out = approve(s, 'a', work, pictures).map((o) => o.msg.t);
  assert.ok(out.includes('rec'));
  assert.ok(out.indexOf('rec') < out.indexOf('pic'));
  setRecording(s, false);
  onHello(s, 'b', {});
  assert.ok(!approve(s, 'b', work, pictures).some((o) => o.msg.t === 'rec')); // 録っていなければ送らない
});

test('録画中の合図は状態の名前だけ（台本・ファイル名を持たない）', () => {
  const s = createSession(1);
  onHello(s, 'a', {}); approve(s, 'a', work, pictures);
  const [{ msg }] = setRecording(s, true);
  assert.deepEqual(Object.keys(msg).sort(), ['on', 't']);
});

// ---------- 形式（G3） ----------

test('形式: MP4 を優先し、録れなければ WebM、どれも録れなければ null', () => {
  assert.deepEqual(pickMime(() => true), { mime: MIMES[0], ext: 'mp4' });
  assert.deepEqual(pickMime((m) => m.startsWith('video/webm')), { mime: 'video/webm;codecs=vp9,opus', ext: 'webm' });
  assert.equal(pickMime(() => false), null);
  assert.equal(pickMime(() => { throw new Error('x'); }), null);
});

test('ファイル名: 作品名と日時。Windows で使えない文字は除く', () => {
  const d = new Date(2026, 9, 24, 9, 5);
  assert.equal(recordName('一億二千万年前へ行く電車', d, 'mp4'), '一億二千万年前へ行く電車-20261024-0905.mp4');
  assert.equal(recordName('a/b:c*?"<>|', d, 'webm'), 'abc-20261024-0905.webm');
  assert.equal(recordName('', d, 'mp4'), 'kamishibai-20261024-0905.mp4');
});

// ---------- 枠（G1） ----------

test('枠: 縦横比を保って 16:9 に収める（聞き手の画面の object-fit: contain と同じ）', () => {
  assert.deepEqual(fitRect(1920, 1080, 1280, 720), { x: 0, y: 0, w: 1280, h: 720 });
  assert.deepEqual(fitRect(1000, 1000, 1280, 720), { x: 280, y: 0, w: 720, h: 720 });   // 正方形は左右が黒
  assert.deepEqual(fitRect(2000, 500, 1280, 720), { x: 0, y: 200, w: 1280, h: 320 });   // 横長は上下が黒
  assert.equal(fitRect(0, 0, 1280, 720), null);                                          // 読み込み前
});

test('枠に描くもの: 動画を始めたら動画（コマが無ければ黒）、それ以外はその枚の絵（無ければ黒）', () => {
  assert.equal(stageSource({ videoStarted: true, videoReady: true, pictureReady: true }), 'video');
  assert.equal(stageSource({ videoStarted: true, videoReady: false, pictureReady: true }), 'black');
  assert.equal(stageSource({ videoStarted: false, videoReady: true, pictureReady: true }), 'picture'); // 動画の枚の再生前は絵
  assert.equal(stageSource({ videoStarted: false, videoReady: true, pictureReady: false }), 'black'); // 絵の無い動画の枚
});

// ---------- 経過時間（P3） ----------

test('経過時間: 開演前は出さない。開演から全体を、枚を動かすたびに「この枚」を数える', () => {
  let c = createClock();
  assert.deepEqual(clockRead(c, 5000), { total: null, slide: null });
  c = clockSlide(c, 6000); // 開演前の枚送りでは始まらない
  assert.deepEqual(clockRead(c, 7000), { total: null, slide: null });
  c = clockStart(c, 10_000);
  assert.deepEqual(clockRead(c, 25_000), { total: 15, slide: 15 });
  c = clockSlide(c, 30_000);
  assert.deepEqual(clockRead(c, 42_000), { total: 32, slide: 12 });
  c = clockStart(c, 50_000); // 開演は1回だけ（押し直しても全体は戻らない）
  assert.deepEqual(clockRead(c, 50_000), { total: 40, slide: 20 });
});

test('経過時間: 時計が戻っても負にしない', () => {
  const c = clockStart(createClock(), 10_000);
  assert.deepEqual(clockRead(c, 9_000), { total: 0, slide: 0 });
});

test('経過時間の時計は数だけを持つ（練習の記録を残す項目が無い＝P4）', () => {
  const c = clockSlide(clockStart(createClock(), 1), 2);
  assert.deepEqual(Object.keys(c).sort(), ['slideAt', 'startedAt']);
});

// ---------- 練習（P1）・録画のボタン（G5） ----------

test('練習中＝受付を開いていない（聞き手の有無ではなく、受付を開いたかで決める）', () => {
  assert.equal(isPractice({ roomOpen: false }), true);
  assert.equal(isPractice({ roomOpen: true }), false);
  assert.equal(isPractice(undefined), true);
});

test('録画のボタン: 受付を開いていなくても押せる。作品が無い・録れない・録りながら保存できないブラウザでは押せない', () => {
  const mime = { mime: MIMES[0], ext: 'mp4' };
  assert.deepEqual(recordable({ hasWork: true, mime, canSave: true }), { ok: true, why: null });
  assert.equal(recordable({ hasWork: false, mime, canSave: true }).why, 'no-work');
  assert.equal(recordable({ hasWork: true, mime: null, canSave: true }).why, 'no-format');
  assert.equal(recordable({ hasWork: true, mime, canSave: false }).why, 'no-save');
});

test('枚を動かしても録画中の状態は変わらない', () => {
  const s = createSession(1);
  setRecording(s, true);
  goTo(s, 2, 3);
  assert.equal(s.recording, true);
});
