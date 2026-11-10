import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  createSession, onHello, approve, reject, goTo, onGot, wouldExceed, welcomeMessage,
  mayOpenBulk, onHave, onVideoFail, playVideo, onSync,
  knownToken, staleTwins, startShow, slideAudio, videoAudio, talkMessage, audioTick, setVolume, onLink,
} from '../../player/js/protocol.js';

const work = {
  format: 'digital-kamishibai/work', version: 1, title: 'T', language: 'en', draft: true,
  // overlays も notes と同じく語り手専用（work-format §3.2。練習しながら直す修正票のために足した）
  slides: [1, 2, 3].map((n) => ({ number: n, title: `S${n}`, picture: `pictures/0${n}.jpg`, notes: `SECRET NOTES ${n}`, overlays: [[[`SECRET OVERLAY ${n}`]]], overlay_base: `overlay_base/SECRET_BASE_${n}.jpg`, overlay_layout: [{ x: 1, y: 1, width: 1, height: 1, inset: [0, 0, 0, 0], anchor: 'top', wrap: true, paragraphs: [{ align: 'left', space_before: 0, size: 30, bold: true, color: '#123456', font: 'SECRETFONT' }] }], cues: [{ type: 'sound', file: 'sounds/x.mp3' }, { type: 'video', file: 'videos/SECRET_VIDEO.mp4', role: 'ending', seats: [{ n: 1, from: 0, to: 5, label: 'SECRET_LABEL.jpg', pin: 'SECRET PIN' }] }, { type: 'video', file: 'videos/clip.mp4', source_segments: [{ start: 4242, dur: 10 }] }] })),
};
const pictures = new Map([1, 2, 3].map((n) => [n, { mime: 'image/jpeg', size: 100 * n, key: `pictures/0${n}.jpg` }]));

function everything(out) { return JSON.stringify(out); }

test('承認前の端末には「待って」しか送らない', () => {
  const s = createSession(2);
  const out = onHello(s, 'a', { name: 'A', device: 'iPhone' });
  assert.deepEqual(out, [{ to: 'a', msg: { t: 'wait' } }]);
  // 承認前に枚を動かしても、その端末には何も行かない
  assert.deepEqual(goTo(s, 2, 3), []);
});

test('断った端末には「断られた」以外を送らない', () => {
  const s = createSession(1);
  onHello(s, 'a', {});
  assert.deepEqual(reject(s, 'a'), [{ to: 'a', msg: { t: 'reject' } }]);
  assert.deepEqual(approve(s, 'a', work, pictures), []);
  assert.deepEqual(goTo(s, 3, 3), []);
});

test('承認した端末には、作品の情報・全部の絵・いまの枚が届く', () => {
  const s = createSession(1);
  onHello(s, 'a', {});
  const out = approve(s, 'a', work, pictures);
  assert.ok(out.every((o) => o.to === 'a'));
  assert.equal(out[0].msg.t, 'welcome');
  assert.deepEqual(out.filter((o) => o.msg.t === 'pic').map((o) => o.msg.n).sort(), [1, 2, 3]);
  assert.deepEqual(out[1].msg, { t: 'slide', n: 1 }); // いまの枚は絵より先（途中から入った端末が、絵の受け取り中に別の枚を報告しないように）
});

test('途中から入った端末には、いまの枚の絵から先に送る', () => {
  const s = createSession(2);
  onHello(s, 'a', {}); approve(s, 'a', work, pictures);
  goTo(s, 2, 3);
  onHello(s, 'b', {});
  const pics = approve(s, 'b', work, pictures).filter((o) => o.msg.t === 'pic').map((o) => o.msg.n);
  assert.deepEqual(pics, [2, 3, 1]);
});

test('R1: 聞き手へ出ていくものに台本・合図・パスが含まれない', () => {
  const s = createSession(3);
  const all = [];
  for (const id of ['a', 'b']) { all.push(...onHello(s, id, {})); all.push(...approve(s, id, work, pictures)); }
  all.push(...goTo(s, 3, 3));
  const text = everything(all);
  assert.ok(!text.includes('SECRET NOTES'));
  assert.ok(!text.includes('notes'));
  assert.ok(!text.includes('SECRET OVERLAY'));
  assert.ok(!text.includes('overlays'));
  assert.ok(!text.includes('overlay_layout') && !text.includes('overlay_base') && !text.includes('SECRET_BASE') && !text.includes('SECRETFONT'));
  assert.ok(!text.includes('draft'));
  assert.ok(!text.includes('sounds/'));
  assert.ok(!text.includes('pictures/'));
  assert.deepEqual(Object.keys(welcomeMessage(work, pictures)).sort(), ['audio', 'count', 'links', 'pictures', 't', 'title', 'videos']);
});

test('R1: エンディング動画の席・写真の名前・元の動画の区間は聞き手へ出ていかない（work-format §3.3）', () => {
  const s = createSession(2);
  // 語り手の側の動画の一覧に合図の中身が混ざっていても（{...v} で広げた形）、拾うのは名指しの項目だけ
  const videos = work.slides[0].cues.filter((c) => c.type === 'video').map((c, k) => ({ ...c, id: `v${k}`, n: 1, size: 10, mime: 'video/mp4', kind: 'video' }));
  const out = [...onHello(s, 'a', {}), ...approve(s, 'a', work, pictures, videos), ...goTo(s, 2, 3)];
  const text = everything(out);
  for (const secret of ['seats', 'SECRET_LABEL', 'label', 'SECRET PIN', 'pin"', 'source_segments', '4242', 'role', 'ending', 'SECRET_VIDEO', 'videos/']) {
    assert.ok(!text.includes(secret), secret);
  }
});

test('枚の合図は承認済みの端末にだけ届く', () => {
  const s = createSession(3);
  onHello(s, 'a', {}); approve(s, 'a', work, pictures);
  onHello(s, 'b', {}); // 承認しない
  onHello(s, 'c', {}); approve(s, 'c', work, pictures); reject(s, 'c'); // 承認後の reject は効かない
  const out = goTo(s, 2, 3);
  assert.deepEqual(out.map((o) => o.to).sort(), ['a', 'c']);
});

test('枚は 1..N の外へ出ない', () => {
  const s = createSession(1);
  assert.deepEqual(goTo(s, 0, 3), []);
  goTo(s, 99, 3);
  assert.equal(s.slide, 3);
});

test('予定台数に達したら、次の承認は「超える」と分かる', () => {
  const s = createSession(1);
  onHello(s, 'a', {});
  assert.equal(wouldExceed(s), false);
  approve(s, 'a', work, pictures);
  onHello(s, 'b', {});
  assert.equal(wouldExceed(s), true);
});

test('名乗りは長さを切る（画面を壊さない）', () => {
  const s = createSession(1);
  onHello(s, 'a', { name: 'x'.repeat(500), device: 'y'.repeat(500) });
  assert.equal(s.peers.get('a').name.length, 40);
  assert.equal(s.peers.get('a').device.length, 40);
});

test('受け取りの数は承認済みの端末だけ数える', () => {
  const s = createSession(1);
  onHello(s, 'a', {});
  onGot(s, 'a', 1);
  assert.equal(s.peers.get('a').received, 0);
  approve(s, 'a', work, pictures);
  onGot(s, 'a', 1);
  assert.equal(s.peers.get('a').received, 1);
});

// ---------- 動画（段階2） ----------

const vids = [{ id: 'v1', n: 3, key: 'videos/secret-path/ending.mp4', size: 1000, mime: 'video/mp4', file: {} }];

test('作品の情報の動画は、id・枚・大きさ・MIME だけ（パスもファイルも渡らない）', () => {
  const w = welcomeMessage(work, pictures, vids);
  assert.deepEqual(w.videos, [{ id: 'v1', n: 3, size: 1000, mime: 'video/mp4' }]);
  assert.ok(!everything(w).includes('secret-path'));
  assert.ok(!everything(w).includes('SECRET NOTES'));
});

test('荷物用の接続は、承認済みの端末からだけ受ける', () => {
  const s = createSession(1);
  assert.equal(mayOpenBulk(s, 'a'), false);
  onHello(s, 'a', {});
  assert.equal(mayOpenBulk(s, 'a'), false);
  approve(s, 'a', work, pictures, vids);
  assert.equal(mayOpenBulk(s, 'a'), true);
  onHello(s, 'b', {});
  reject(s, 'b');
  assert.equal(mayOpenBulk(s, 'b'), false);
});

test('承認していない端末の申告では、運び方を決めない', () => {
  const s = createSession(1);
  onHello(s, 'a', {});
  assert.deepEqual(onHave(s, 'a', { store: 'opfs', items: [] }, vids), []);
  approve(s, 'a', work, pictures, vids);
  assert.deepEqual(onHave(s, 'a', { store: 'opfs', free: 1e9, items: [] }, vids),
    [{ to: 'a', msg: { t: 'vmode', id: 'v1', mode: 'stored', reason: null } }]);
  assert.equal(s.peers.get('a').plan[0].from, 0);
});

test('保存に失敗した端末は、その動画だけ「その場で流す」へ', () => {
  const s = createSession(1);
  onHello(s, 'a', {});
  approve(s, 'a', work, pictures, vids);
  onHave(s, 'a', { store: 'opfs', free: 1e9, items: [] }, vids);
  assert.deepEqual(onVideoFail(s, 'a', 'v1'), [{ to: 'a', msg: { t: 'vmode', id: 'v1', mode: 'stream', reason: 'store-failed' } }]);
  assert.deepEqual(onVideoFail(s, 'a', 'v1'), []);
});

test('再生の合図は承認済みの端末にだけ届き、途中から入った端末にも承認のときに届く', () => {
  const s = createSession(2);
  onHello(s, 'a', {});
  approve(s, 'a', work, pictures, vids);
  onHello(s, 'p', {}); // 承認待ち
  const out = playVideo(s, 'play', { id: 'v1', pos: 5, now: 1000 });
  assert.deepEqual(out, [{ to: 'a', msg: { t: 'vstate', id: 'v1', playing: true, pos: 5 } }]);
  const late = approve(s, 'p', work, pictures, vids, 3000);
  assert.deepEqual(late.at(-1).msg, { t: 'vstate', id: 'v1', playing: true, pos: 7 });
  // 止めたあとに入った端末には、動画の合図を送らない
  playVideo(s, 'stop', { now: 4000 });
  onHello(s, 'c', {});
  assert.ok(approve(s, 'c', work, pictures, vids, 5000).every((o) => o.msg.t !== 'vstate'));
});

test('「いまの位置を」の頼みには、承認済みの端末にだけ、その瞬間の位置を返す', () => {
  const s = createSession(2);
  onHello(s, 'a', {});
  approve(s, 'a', work, pictures, vids);
  assert.deepEqual(onSync(s, 'a', 0), []); // 再生していなければ何も返さない
  playVideo(s, 'play', { id: 'v1', pos: 10, now: 1000 });
  assert.deepEqual(onSync(s, 'a', 3500), [{ to: 'a', msg: { t: 'vstate', id: 'v1', playing: true, pos: 12.5 } }]);
  onHello(s, 'x', {});
  assert.deepEqual(onSync(s, 'x', 3500), []);
});

// ---------- 音と途中復帰（段階4） ----------

const audioWork = {
  ...work,
  slides: [
    { number: 1, title: '', picture: 'p1', notes: '', cues: [{ type: 'bgm', file: 'sounds/a.mp3', loop: false }, { type: 'sound', file: 'sounds/s.mp3' }] },
    { number: 2, title: '', picture: 'p2', notes: '', cues: [] },
    { number: 3, title: '', picture: 'p3', notes: '', cues: [{ type: 'bgm-stop' }] },
  ],
};
const idOf = (f) => ({ 'sounds/a.mp3': 'A', 'sounds/s.mp3': 'S' })[f] || null;

test('作品の情報の音は、id・大きさ・MIME だけ（パスは渡らない）', () => {
  const w = welcomeMessage(work, pictures, [...vids, { id: 'A', kind: 'audio', key: 'sounds/secret.mp3', size: 9, mime: 'audio/mpeg' }]);
  assert.deepEqual(w.audio, [{ id: 'A', size: 9, mime: 'audio/mpeg', gain: 0 }]);
  assert.equal(w.videos.length, 1);
  assert.ok(!everything(w).includes('secret'));
});

test('大きすぎる BGM を下げる量（dB）も渡す。上げる値・数でない値は 0 に、下げすぎは 40dB に収める', () => {
  const a = (id, gain) => ({ id, kind: 'audio', key: `sounds/${id}.mp3`, size: 9, mime: 'audio/mpeg', gain });
  const w = welcomeMessage(work, pictures, [a('A', -18.3), a('B', 6), a('C', 'x'), a('D', -90)]);
  assert.deepEqual(w.audio.map((x) => x.gain), [-18.3, 0, 0, -40]);
});

test('開演するまで、音の合図はどこにも出ない', () => {
  const s = createSession(1);
  onHello(s, 'a', {});
  approve(s, 'a', audioWork, pictures, []);
  assert.deepEqual(slideAudio(s, audioWork, idOf, 0), []);
  assert.deepEqual(audioTick(s, 0), []);
  assert.deepEqual(onSync(s, 'a', 0), []);
  const out = startShow(s, audioWork, idOf, 1000);
  assert.deepEqual(out.map((o) => o.msg), [
    { t: 'astate', id: 'A', loop: false, playing: true, pos: 0 },
    { t: 'sound', id: 'S' },
  ]);
  assert.deepEqual(startShow(s, audioWork, idOf, 2000), []); // 2回押しても鳴らし直さない
});

test('枚を動かすと、曲が変わったときだけ BGM の合図、その枚の効果音を送る', () => {
  const s = createSession(1);
  onHello(s, 'a', {});
  approve(s, 'a', audioWork, pictures, []);
  startShow(s, audioWork, idOf, 0);
  goTo(s, 2, 3);
  assert.deepEqual(slideAudio(s, audioWork, idOf, 5000), []); // 同じ曲のまま
  goTo(s, 3, 3);
  assert.deepEqual(slideAudio(s, audioWork, idOf, 6000).map((o) => o.msg), [{ t: 'astate', id: null, loop: false, playing: false, pos: 0 }]);
  goTo(s, 1, 3);
  const back = slideAudio(s, audioWork, idOf, 7000).map((o) => o.msg);
  assert.deepEqual(back, [{ t: 'astate', id: 'A', loop: false, playing: true, pos: 0 }, { t: 'sound', id: 'S' }]);
});

test('動画を流し始めたら BGM を止める合図を送り、同じ曲の続く枚へ移っても鳴らし直さない', () => {
  const s = createSession(1);
  onHello(s, 'a', {});
  approve(s, 'a', audioWork, pictures, []);
  assert.deepEqual(videoAudio(s, audioWork, 0), [], '開演前は何も送らない');
  startShow(s, audioWork, idOf, 0);
  assert.deepEqual(videoAudio(s, audioWork, 3000).map((o) => o.msg), [{ t: 'astate', id: null, loop: false, playing: false, pos: 0 }]);
  assert.deepEqual(videoAudio(s, audioWork, 4000), [], '2回目は送らない');
  goTo(s, 2, 3);
  assert.deepEqual(slideAudio(s, audioWork, idOf, 5000), [], '動画のあとも、同じ曲は鳴らし直さない');
  // 途中から入った端末にも、止まったままが届く
  onHello(s, 'b', {});
  assert.deepEqual(approve(s, 'b', audioWork, pictures, [], 6000).at(-1).msg, { t: 'astate', id: null, loop: false, playing: false, pos: 0 });
});

test('話している／いないの合図は承認済みの聞き手にだけ・中身は on だけ（声の大きさは送らない）', () => {
  const s = createSession(2);
  onHello(s, 'a', {});
  onHello(s, 'b', {});
  approve(s, 'a', audioWork, pictures, []);
  assert.deepEqual(talkMessage(s, true), [{ to: 'a', msg: { t: 'talk', on: true } }]);
  assert.deepEqual(talkMessage(s, false).map((o) => o.msg), [{ t: 'talk', on: false }]);
});

test('途中から入った端末には、承認のときに今の曲と位置が届く', () => {
  const s = createSession(2);
  onHello(s, 'a', {});
  approve(s, 'a', audioWork, pictures, []);
  startShow(s, audioWork, idOf, 1000);
  onHello(s, 'b', {});
  assert.deepEqual(approve(s, 'b', audioWork, pictures, [], 4000).at(-1).msg, { t: 'astate', id: 'A', loop: false, playing: true, pos: 3 });
  assert.deepEqual(onSync(s, 'b', 5000).map((o) => o.msg), [{ t: 'astate', id: 'A', loop: false, playing: true, pos: 4 }]);
});

test('合い札: 承認した端末のものだけが通り、短いもの・断った端末のものは通らない', () => {
  const s = createSession(2);
  const tok = 'x'.repeat(32);
  onHello(s, 'a', { token: tok });
  assert.equal(knownToken(s, tok), false); // 承認前
  approve(s, 'a', work, pictures);
  assert.equal(knownToken(s, tok), true);
  onHello(s, 'b', { token: 'y'.repeat(32) });
  reject(s, 'b');
  assert.equal(knownToken(s, 'y'.repeat(32)), false);
  onHello(s, 'c', { token: 'short' });
  approve(s, 'c', work, pictures);
  assert.equal(knownToken(s, 'short'), false);
  assert.equal(knownToken(s, undefined), false);
  // 別の上演（新しい受付）では使えない
  assert.equal(knownToken(createSession(1), tok), false);
});

// ---------- 当日の音量つまみ（音量の釣り合い L5） ----------

test('音量の合図は承認済みの端末にだけ届き、範囲の外は切り詰める', () => {
  const s = createSession(2);
  onHello(s, 'a', {});
  approve(s, 'a', work, pictures);
  onHello(s, 'p', {}); // 承認待ち
  assert.deepEqual(setVolume(s, 3, -1), [{ to: 'a', msg: { t: 'volume', music: 2, video: 0 } }]);
  assert.deepEqual(setVolume(s, 'x', 0.5)[0].msg, { t: 'volume', music: 1, video: 0.5 });
});

test('途中から入った端末には、変えてある音量が承認のときに届く（変えていなければ送らない）', () => {
  const s = createSession(2);
  onHello(s, 'a', {});
  assert.ok(approve(s, 'a', work, pictures).every((o) => o.msg.t !== 'volume'));
  setVolume(s, 1.5, 0.6);
  onHello(s, 'b', {});
  assert.deepEqual(approve(s, 'b', work, pictures).at(-1).msg, { t: 'volume', music: 1.5, video: 0.6 });
});

test('入り直した端末と同じ合い札の古い記録を見つける（承認していない合い札では見つけない）', () => {
  const s = createSession(2);
  const tok = 'z'.repeat(32);
  onHello(s, 'old', { token: tok });
  assert.deepEqual(staleTwins(s, 'new', tok), []); // 承認前の合い札は通らない
  approve(s, 'old', work, pictures);
  onHello(s, 'other', { token: 'w'.repeat(32) });
  approve(s, 'other', work, pictures);
  onHello(s, 'new', { token: tok });
  assert.deepEqual(staleTwins(s, 'new', tok), ['old']);
  assert.deepEqual(staleTwins(s, 'new', 'q'.repeat(32)), []);
});

// ---------- リンクの動画（work-format §2.4・§3.3） ----------

const linkWork = {
  format: 'digital-kamishibai/work', version: 1, title: 'T', language: 'en',
  slides: [
    { number: 1, title: 'A', picture: 'pictures/01.jpg', notes: 'SECRET NOTES', cues: [] },
    { number: 2, title: 'B', picture: 'pictures/02.jpg', notes: '', cues: [
      { type: 'video', file: 'videos/SECRET_FILE.mp4' },
      { type: 'video', url: 'https://www.youtube.com/watch?v=8KkKuTCFvzI&list=SECRETLIST', start: 351, end: 369, captions: 'ja' },
    ] },
    { number: 3, title: 'C', picture: null, notes: '', cues: [{ type: 'video', url: 'https://youtu.be/dCVlRFWOjgE', volume: -6 }] },
  ],
};

test('リンクの動画は、YouTube の ID と流す範囲だけが聞き手へ届く（リンクの文字そのものは送らない）', () => {
  const s = createSession(1);
  const out = [...onHello(s, 'a', {}), ...approve(s, 'a', linkWork, new Map())];
  const welcome = out.find((o) => o.msg.t === 'welcome').msg;
  assert.deepEqual(welcome.links, [
    { id: 'link-2-2', n: 2, yt: '8KkKuTCFvzI', start: 351, end: 369, captions: 'ja', volume: 0 },
    { id: 'link-3-1', n: 3, yt: 'dCVlRFWOjgE', start: 0, end: null, captions: null, volume: -6 },
  ]);
  const text = everything(out);
  for (const secret of ['SECRETLIST', 'youtube.com', 'youtu.be', 'SECRET_FILE', 'SECRET NOTES']) assert.ok(!text.includes(secret), secret);
});

test('リンクの動画を流せるかの知らせは、承認済みの端末のものだけ受ける（R7）', () => {
  const s = createSession(2);
  onHello(s, 'a', {}); approve(s, 'a', linkWork, new Map());
  onHello(s, 'b', {}); // 承認しない
  assert.equal(onLink(s, 'b', { t: 'link', id: 'link-2-2', ok: false, reason: 'blocked' }), false);
  assert.equal(s.peers.get('b').links, undefined);
  assert.equal(onLink(s, 'a', { t: 'link', id: 'link-2-2', ok: false, reason: 'blocked' }), true);
  assert.equal(onLink(s, 'a', { t: 'link', id: '*', ok: false, reason: 'no-such-reason' }), true); // 知らない理由は 'player'
  assert.deepEqual(s.peers.get('a').links, { 'link-2-2': 'blocked', '*': 'player' });
  assert.equal(onLink(s, 'a', { t: 'link', id: 'link-2-2', ok: true }), true); // 流せるようになった
  assert.equal(s.peers.get('a').links['link-2-2'], null);
  assert.equal(onLink(s, 'a', { t: 'link', id: 'x'.repeat(41), ok: true }), false); // 長すぎる id は受けない
});

test('リンクの動画でも、再生の合図はファイルの動画と同じ形', () => {
  const s = createSession(1);
  onHello(s, 'a', {}); approve(s, 'a', linkWork, new Map());
  const out = playVideo(s, 'play', { id: 'link-2-2', pos: 351, now: 1000 });
  assert.deepEqual(out, [{ to: 'a', msg: { t: 'vstate', id: 'link-2-2', playing: true, pos: 351 } }]);
});
