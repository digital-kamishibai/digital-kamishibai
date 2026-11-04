import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  createVoice, heardFrom, routes, voiceMessages, toneLevel, toneHeard, rollOrder, judgeRollCall, TONE_HZ, TONE_DB,
} from '../../player/js/voice.js';
import { createSession, onHello, approve, reject, onView, onHeard } from '../../player/js/protocol.js';

const work = {
  format: 'digital-kamishibai/work', version: 1, title: 'T', language: 'en',
  slides: [1, 2].map((n) => ({ number: n, title: `S${n}`, picture: `pictures/0${n}.jpg`, notes: 'N', cues: [] })),
};
const pictures = new Map([1, 2].map((n) => [n, { mime: 'image/jpeg', size: 10, key: `pictures/0${n}.jpg` }]));
const view = (mic) => ({ t: 'view', slide: 1, show: 'picture', sound: 'on', mic, recv: { got: 0, all: 0 } });

/** 承認済み a・b・c（マイク: a=on, b=on, c=listen）と、承認待ち d（マイク on） */
function room() {
  const s = createSession(3);
  for (const id of ['a', 'b', 'c', 'd']) onHello(s, id, { name: id });
  for (const id of ['a', 'b', 'c']) approve(s, id, work, pictures);
  onView(s, 'a', view('on'));
  onView(s, 'b', view('on'));
  onView(s, 'c', view('listen'));
  return s;
}

test('届け先: 自分の声は自分に返らない・聞くだけの端末の声は誰にも届かない', () => {
  const s = room();
  const r = routes(s.peers, createVoice());
  assert.deepEqual(r.narrator, ['a', 'b']);
  assert.deepEqual(r.listeners.a, { narrator: true, from: ['b'] });
  assert.deepEqual(r.listeners.b, { narrator: true, from: ['a'] });
  assert.deepEqual(r.listeners.c, { narrator: true, from: ['a', 'b'] }); // 聞くだけでも、ほかの声は聞こえる
});

test('届け先（R7）: 承認していない端末・断った端末は表に入らず、その声もどこにも届かない', () => {
  const s = room();
  assert.equal(onView(s, 'd', view('on')), false); // 承認待ちの報告は捨てられる
  s.peers.get('d').view = view('on');               // 仮に報告が残っていても
  onHello(s, 'e', {}); reject(s, 'e');
  const r = routes(s.peers, createVoice());
  assert.equal('d' in r.listeners, false);
  assert.equal('e' in r.listeners, false);
  assert.ok(!r.narrator.includes('d'));
  assert.ok(Object.values(r.listeners).every((x) => !x.from.includes('d')));
  assert.equal(heardFrom(s.peers.get('d'), createVoice()).reason, 'not-approved');
});

test('届け先: マイクを切った・許可されていない・マイクが無い端末の声は届かない', () => {
  const s = room();
  for (const mic of ['off', 'denied', 'none']) {
    onView(s, 'a', view(mic));
    assert.deepEqual(heardFrom(s.peers.get('a'), createVoice()), { heard: false, reason: 'mic' });
  }
});

test('届け先（V6）: 動画のあいだは聞き手の声が誰にも届かず、語り手の声は届く', () => {
  const s = room();
  const r = routes(s.peers, createVoice(), { video: true });
  assert.deepEqual(r.narrator, []);
  assert.ok(Object.values(r.listeners).every((x) => x.narrator && x.from.length === 0));
  assert.equal(heardFrom(s.peers.get('a'), createVoice(), { video: true }).reason, 'video');
});

test('届け先（V5）: 語り手が止めた声は誰にも届かない（札ごと・まとめて）。語り手の端末のマイクには触らない', () => {
  const s = room();
  const v = createVoice();
  v.held.add('a');
  let r = routes(s.peers, v);
  assert.deepEqual(r.narrator, ['b']);
  assert.deepEqual(r.listeners.c.from, ['b']);
  assert.equal(heardFrom(s.peers.get('a'), v).reason, 'held');
  v.held.clear();
  v.allHeld = true;
  r = routes(s.peers, v);
  assert.deepEqual(r.narrator, []);
  v.narratorMic = false;
  r = routes(s.peers, v);
  assert.ok(Object.values(r.listeners).every((x) => !x.narrator));
});

test('届け先（V7）: BGM のあいだは、最初は届ける。切り替えると届けない', () => {
  const s = room();
  const v = createVoice();
  assert.equal(heardFrom(s.peers.get('a'), v, { bgm: true }).heard, true);
  v.bgmHold = true;
  assert.deepEqual(heardFrom(s.peers.get('a'), v, { bgm: true }), { heard: false, reason: 'bgm' });
  assert.equal(heardFrom(s.peers.get('a'), v, { bgm: false }).heard, true);
});

test('届け先（V9）: 同じ部屋と分かった端末の声は届かない（語り手が戻せる）', () => {
  const s = room();
  const v = createVoice();
  v.sameRoom.add('b');
  assert.equal(heardFrom(s.peers.get('b'), v).reason, 'same-room');
  v.sameRoom.delete('b');
  assert.equal(heardFrom(s.peers.get('b'), v).heard, true);
});

test('声の合図: 変わった端末にだけ送り、承認していない端末へは送らない', () => {
  const s = room();
  const v = createVoice();
  const prev = new Map();
  let out = voiceMessages(s.peers, v, {}, prev);
  assert.deepEqual(out.map((o) => o.to).sort(), ['a', 'b', 'c']);
  assert.deepEqual(out.find((o) => o.to === 'a').msg, { t: 'voice', heard: true, reason: null, quiet: false });
  assert.deepEqual(voiceMessages(s.peers, v, {}, prev), []);
  out = voiceMessages(s.peers, v, { video: true }, prev);
  assert.deepEqual(out.map((o) => o.to).sort(), ['a', 'b']); // c は聞くだけのまま（理由が変わらない）
  assert.deepEqual(out[0].msg, { t: 'voice', heard: false, reason: 'video', quiet: false });
  // 語り手の声を鳴らさない端末になったら、その端末にだけ知らせる（聞くだけの c でも）
  v.quiet.add('c');
  out = voiceMessages(s.peers, v, { video: true }, prev);
  assert.deepEqual(out, [{ to: 'c', msg: { t: 'voice', heard: false, reason: 'mic', quiet: true } }]);
});

test('届け先: 語り手と同じ部屋の端末へは語り手の声を送らない。ほかの端末と、その端末の声はそのまま', () => {
  const s = room();
  const v = createVoice();
  v.quiet.add('a');
  const r = routes(s.peers, v);
  assert.equal(r.listeners.a.narrator, false);
  assert.equal(r.listeners.b.narrator, true);
  assert.equal(r.listeners.c.narrator, true);
  assert.deepEqual(r.narrator, ['a', 'b']); // a の声は止めない（止めるのは sameRoom）
  assert.deepEqual(r.listeners.a.from, ['b']);
  v.quiet.delete('a');
  assert.equal(routes(s.peers, v).listeners.a.narrator, true);
});

// ---------- 音の点呼 ----------

test('点呼: 確かめの音の高さが、まわりより何 dB 大きいか', () => {
  const sr = 48000, fft = 2048, n = fft / 2;
  const quiet = new Array(n).fill(-100);
  assert.equal(toneLevel(quiet, sr, fft), 0);
  const loud = quiet.slice();
  loud[Math.round((TONE_HZ * fft) / sr)] = -60;
  assert.equal(toneLevel(loud, sr, fft), 40);
  assert.equal(toneHeard(40), true);
  assert.equal(toneHeard(TONE_DB - 1), false);
  assert.equal(toneHeard(null), false);
  assert.equal(toneLevel([], sr, fft), 0);
});

test('点呼: 順番は語り手 → 承認済みの聞き手（聞くだけの端末も鳴らす——スピーカーは持っている。承認待ちは鳴らさない）', () => {
  assert.deepEqual(rollOrder(room().peers), ['narrator', 'a', 'b', 'c']);
});

test('点呼の判定: 同じ部屋の組を見つけ、後から入ったほうを止める', () => {
  const joined = new Map([['a', 1], ['b', 2], ['c', 3]]);
  const loud = TONE_DB + 10;
  const r = judgeRollCall([
    { source: 'narrator', levels: { narrator: 2, a: 1, b: 0 } },
    { source: 'a', levels: { narrator: 0, b: loud, c: 3 } },
    { source: 'b', levels: { narrator: 0, a: loud } }, // 同じ組をもう一度拾っても1組
  ], joined);
  assert.equal(r.speaker, false);
  assert.deepEqual(r.pairs, [['a', 'b']]);
  assert.deepEqual(r.hold, ['b']);
  assert.deepEqual(r.quiet, []); // 語り手と同じ部屋の端末は無い
});

test('点呼の判定: 語り手のマイクが自分の音を拾ったらスピーカー。語り手と同じ部屋なら聞き手のほうを止める', () => {
  const loud = TONE_DB + 5;
  const r = judgeRollCall([{ source: 'narrator', levels: { narrator: loud, a: loud } }], new Map([['a', 1]]));
  assert.equal(r.speaker, true);
  assert.deepEqual(r.pairs, [['narrator', 'a']]);
  assert.deepEqual(r.hold, ['a']);
  assert.deepEqual(r.quiet, ['a']); // その端末では語り手の声を鳴らさない（ハウリング止め）
  // 誰も拾わなければ何も止めない
  assert.deepEqual(judgeRollCall([{ source: 'a', levels: { b: 1 } }], new Map()), { speaker: false, pairs: [], hold: [], quiet: [] });
});

test('点呼の判定: 聞くだけの端末の音を語り手のマイクが拾ったら、その端末で語り手の声を鳴らさない', () => {
  // c は聞くだけ（マイクなし）なので測る側にはならないが、鳴らした音を語り手が拾える
  const loud = TONE_DB + 8;
  const r = judgeRollCall([
    { source: 'narrator', levels: { narrator: 0, a: 0 } },
    { source: 'a', levels: { narrator: 0 } },
    { source: 'c', levels: { narrator: loud, a: 0 } },
  ], new Map([['a', 1], ['c', 2]]));
  assert.deepEqual(r.pairs, [['c', 'narrator']]);
  assert.deepEqual(r.quiet, ['c']);
  assert.equal(r.speaker, false);
});

test('点呼の返事（heard）は承認済みの端末のものだけ受ける', () => {
  const s = room();
  assert.equal(onHeard(s, 'd', { t: 'heard', round: 1, level: 30 }), null);
  assert.equal(onHeard(s, 'zz', { t: 'heard', round: 1, level: 30 }), null);
  assert.deepEqual(onHeard(s, 'a', { t: 'heard', round: 1, level: 30 }), { round: 1, level: 30 });
  assert.deepEqual(onHeard(s, 'a', { t: 'heard', round: 2, level: 'x' }), { round: 2, level: null });
});
