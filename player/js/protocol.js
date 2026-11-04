// 語り手と聞き手のあいだの取り決めと、語り手側の受付の状態。
// DOM にも通信にも触らない。「誰に何を送るか」はすべてここで決め、通信の層はそれを運ぶだけにする
// ——R1（台本は聞き手へ渡らない）と R7（承認した端末にだけ送る）を、画面ではなくデータで守るため。

import { planTransfers } from './transfer.js';
import { createPlayback, command, vstate } from './playback.js';
import { createAudio, start, retune, cutForVideo, afterVideo, astate, soundMessages } from './audio.js';
import { cleanView } from './view.js';

export const PROTOCOL = 1;

// 語り手 → 聞き手
//   { t: 'wait' }                                   承認待ち
//   { t: 'reject' }                                 断られた
//   { t: 'welcome', title, count, pictures:[{n, mime, size}], videos:[{id, n, size, mime}] }
//   { t: 'pic', n, mime, data }                     絵1枚（data は通信の層が詰める）
//   { t: 'slide', n }                               いまの枚
//   { t: 'vmode', id, mode, reason }                この端末への動画の運び方（'stored' | 'stream'）
//   { t: 'vstate', id, playing, pos }               動画の再生の合図（playback.js）
//   { t: 'astate', id, loop, playing, pos }         BGM の合図（audio.js。id が null なら無音）
//   { t: 'sound', id }                              効果音を1回鳴らす
//   { t: 'bye' }                                    語り手が画面を閉じる（上演の終わり）
//   { t: 'volume', music, video }                   当日の音量つまみ（music＝BGM・効果音 0〜2、video＝動画 0〜1。その上演のあいだだけ）
//   { t: 'voice', heard, reason, quiet }            いまあなたの声は届いているか（段階3 V5〜V9。voice.js）。
//                                                   quiet＝語り手と同じ部屋なので、この端末では語り手の声を鳴らしていない
//   { t: 'listen', round, ms }                      音の点呼: これから ms のあいだマイクの音を測って返して
//   { t: 'tone', round }                            音の点呼: 確かめの音を1回鳴らして
//   { t: 'rec', on }                                語り手が録画している（録画と練習 G4。聞き手の画面の隅に「録画中」）
// 聞き手 → 語り手
//   { t: 'hello', v, name, device }
//   { t: 'got', n }                                 絵を1枚受け取った
//   { t: 'have', store, free, items:[{id, bytes}] } 保存先の有無・空き容量・持っている分（入り直しの続きに使う）
//   { t: 'vgot', id, bytes }                        端末に書けた分
//   { t: 'vfail', id }                              保存に失敗した（予備の「その場で流す」へ）
//   { t: 'sync' }                                   動画・音の準備ができた——いまの再生位置をください
//   { t: 'hello', ..., token }                      token＝その上演のあいだの合い札（途中復帰。下の knownToken）
//   { t: 'unlocked' }                               この端末は音を出せるようになった（画面に触れた）
//   { t: 'view', slide, show, sound, mic, playing?, recv:{got, all} }
//                                                   いま自分の画面に出しているもの（view.js。画面が変わったときだけ。絵そのものは送らない）
//   { t: 'quiet', on }                              この端末で語り手の声を鳴らさない（on）／鳴らす（音の点呼の判定を本人が直す）
//   { t: 'heard', round, level }                    音の点呼で、確かめの音をどれだけ拾ったか（dB。マイクが無ければ null）
// 声の通話（段階3 V2。PeerJS の call・metadata { kind: 'voice' }）: 承認したときに語り手から張る。
//   語り手 → 聞き手: 語り手の声＋その聞き手以外の聞き手の声（語り手の PC で混ぜる）／聞き手 → 語り手: その聞き手のマイク
// 荷物用の2本目の接続（label 'bulk'・serialization 'raw'。承認済みの端末からだけ受ける）
//   語り手 → 聞き手: '{"t":"begin","id","from","size"}' → ArrayBuffer（64KB ずつ）… → '{"t":"end","id"}'

/** 聞き手へ渡してよい作品の情報だけを、項目を名指しで拾って作る（台本・合図・パスは入らない）。
 *  動画も番号・大きさ・MIME と、パスを含まない見分け用の id だけ。 */
export function welcomeMessage(work, pictures, media = []) {
  const videos = media.filter((m) => m.kind !== 'audio');
  const audio = media.filter((m) => m.kind === 'audio');
  return {
    t: 'welcome',
    title: String(work.title),
    count: work.slides.length,
    pictures: [...pictures.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([n, p]) => ({ n, mime: String(p.mime), size: Number(p.size) || 0 })),
    videos: videos.map((v) => ({ id: String(v.id), n: Number(v.n), size: Number(v.size) || 0, mime: String(v.mime || 'video/mp4') })),
    audio: audio.map((a) => ({ id: String(a.id), size: Number(a.size) || 0, mime: String(a.mime || 'audio/mpeg') })),
  };
}

export function createSession(expected = 1) {
  return {
    expected: Math.max(0, expected | 0), slide: 1, peers: new Map(), playback: createPlayback(), audio: createAudio(), volume: { music: 1, video: 1 },
    tokens: new Set(),   // 承認した端末の合い札（この上演のあいだだけ。語り手のメモリにしか無い）
    recording: false,    // 語り手が録画している（G4）
  };
}

const approvedPeers = (s) => [...s.peers.values()].filter((p) => p.status === 'approved');

export const approvedCount = (s) => [...s.peers.values()].filter((p) => p.status === 'approved').length;

/** 予定台数を超える承認になるか（承認画面で目立たせる） */
export const wouldExceed = (s) => approvedCount(s) >= s.expected;

function clip(v, n) { return String(v == null ? '' : v).slice(0, n); }

/** 新しい端末が名乗った。承認までは「待って」しか送らない。 */
export function onHello(s, id, hello) {
  const prev = s.peers.get(id);
  if (prev && prev.status === 'approved') return [];
  s.peers.set(id, {
    id,
    name: clip(hello && hello.name, 40),
    device: clip(hello && hello.device, 40),
    status: 'pending',
    received: 0,
    token: clip(hello && hello.token, 64),
    plan: null,        // 動画ごとの運び方（onHave が決める）
  });
  return [{ to: id, msg: { t: 'wait' } }];
}

/** 承認した端末にだけ、作品の情報・絵・いまの枚（と、動画を再生中ならその合図）を送る。 */
export function approve(s, id, work, pictures, videos = [], now = 0) {
  const p = s.peers.get(id);
  if (!p || p.status !== 'pending') return [];
  p.status = 'approved';
  if (p.token.length >= 16) s.tokens.add(p.token);
  // いまの枚は絵より先に知らせる。⚠️ 絵（数MB）の後ろに並べると、途中から入った端末は絵を受け取るあいだ
  // 「1枚目」のつもりでいて、語り手の札に食い違いとして出た（2026-10-24 語り手の画面の作り直しの確認）
  const out = [{ to: id, msg: welcomeMessage(work, pictures, videos) }, { to: id, msg: { t: 'slide', n: s.slide } }];
  // いまの枚から先に送る（途中から入った端末が早く絵を出せるように）
  const order = [...pictures.keys()].sort((a, b) => a - b);
  order.sort((a, b) => (a >= s.slide ? 0 : 1) - (b >= s.slide ? 0 : 1) || a - b);
  for (const n of order) out.push({ to: id, msg: { t: 'pic', n } });
  if (s.playback.id) out.push({ to: id, msg: vstate(s.playback, now) });
  if (s.audio.started) out.push({ to: id, msg: astate(s.audio, now) });
  if (s.volume.music !== 1 || s.volume.video !== 1) out.push({ to: id, msg: { t: 'volume', ...s.volume } });
  // 録画中なら、途中から入った端末・入り直した端末にも最初に知らせる（絵の後ろに並べると、受け取るあいだ知らないまま録られる）
  if (s.recording) out.splice(2, 0, { to: id, msg: { t: 'rec', on: true } });
  return out;
}

/** 録画を始めた・止めた（G4）。**承認済みの端末にだけ**知らせる（承認待ち・断った端末へは送らない。R7）。
 *  受付を開いていない（練習）なら、送る先は無い */
export function setRecording(s, on) {
  s.recording = !!on;
  return approvedPeers(s).map((p) => ({ to: p.id, msg: { t: 'rec', on: s.recording } }));
}

const clamp = (v, lo, hi, d) => (Number.isFinite(+v) ? Math.min(hi, Math.max(lo, +v)) : d);

/** 当日の音量つまみ（音量の釣り合い L5）。承認済みの端末にだけ届く。作品フォルダは変えない */
export function setVolume(s, music, video) {
  s.volume = { music: clamp(music, 0, 2, 1), video: clamp(video, 0, 1, 1) };
  return approvedPeers(s).map((p) => ({ to: p.id, msg: { t: 'volume', ...s.volume } }));
}

/** 途中復帰（R8・P10）: この上演で承認した端末の合い札か。合っていれば語り手は承認なしで入れる。
 *  合い札は聞き手が作った乱数（16文字以上）で、語り手のメモリにしか無い——受付を閉じれば全部無効 */
export const knownToken = (s, token) => typeof token === 'string' && token.length >= 16 && s.tokens.has(token.slice(0, 64));

/** 同じ合い札を持つ、ほかの端末の記録（＝入り直す前の古い接続）。語り手はこれを片付ける。
 *  ⚠️ 相手が切れても PeerJS は知らせないことがあるので、放っておくと同じ端末が一覧に2台並び、承認済みの台数も多く数える */
export function staleTwins(s, id, token) {
  if (!knownToken(s, token)) return [];
  const tok = token.slice(0, 64);
  return [...s.peers.values()].filter((p) => p.id !== id && p.token === tok).map((p) => p.id);
}

/** 荷物用の接続を受けてよい端末か（承認済みだけ。R7） */
export const mayOpenBulk = (s, id) => { const p = s.peers.get(id); return !!p && p.status === 'approved'; };

/** 聞き手が保存先と持っている分を申告した → 動画ごとの運び方を決めて知らせる。
 *  戻り値の msg に加えて、送り始める位置は p.plan に残す（通信の層が読む） */
export function onHave(s, id, have, videos) {
  const p = s.peers.get(id);
  if (!p || p.status !== 'approved') return [];
  p.plan = planTransfers(videos, have);
  return p.plan.map((x) => ({ to: id, msg: { t: 'vmode', id: x.id, mode: x.mode, reason: x.reason } }));
}

/** 保存に失敗した端末を、その動画だけ「その場で流す」へ回す */
export function onVideoFail(s, id, vid) {
  const p = s.peers.get(id);
  const x = p && p.status === 'approved' && p.plan && p.plan.find((v) => v.id === vid);
  if (!x || x.mode === 'stream') return [];
  x.mode = 'stream';
  x.reason = 'store-failed';
  return [{ to: id, msg: { t: 'vmode', id: vid, mode: 'stream', reason: 'store-failed' } }];
}

/** 聞き手が動画の準備を終えて、いまの位置を求めた。承認済みの端末にだけ、その瞬間の位置を返す。
 *  ⚠️ 承認のときの合図は絵（数MB）の後ろに並んで届くので、届いた時点で数秒古い（2026-10-24 実測 2.5秒）。
 *  準備ができた端末から頼まれたときには送り待ちが空なので、新しい位置がすぐ届く */
export function onSync(s, id, now) {
  const p = s.peers.get(id);
  if (!p || p.status !== 'approved') return [];
  const out = [];
  if (s.playback.id) out.push({ to: id, msg: vstate(s.playback, now) });
  if (s.audio.started) out.push({ to: id, msg: astate(s.audio, now) });
  return out;
}

const toApproved = (s, msgs) => approvedPeers(s).flatMap((p) => msgs.map((msg) => ({ to: p.id, msg })));

/** 開演（P1）。押すまでは、どの端末でも BGM・効果音を鳴らさない。idOf(file) → 配った素材の id */
export function startShow(s, work, idOf, now) {
  if (s.audio.started) return [];
  s.audio = start(s.audio, work, s.slide, idOf, now);
  return toApproved(s, [astate(s.audio, now), ...soundMessages(s.audio, work, s.slide, idOf)]);
}

/** 枚を動かしたあとに呼ぶ: BGM を決め直し（変わったときだけ合図）、その枚の効果音を鳴らす（P3） */
export function slideAudio(s, work, idOf, now) {
  const before = s.audio;
  s.audio = retune(s.audio, work, s.slide, idOf, now);
  const msgs = [];
  if (s.audio !== before) msgs.push(astate(s.audio, now));
  msgs.push(...soundMessages(s.audio, work, s.slide, idOf));
  return toApproved(s, msgs);
}

/** 動画を流し始めた: BGM を止める合図（止めるものがあったときだけ）。動画のあとも、次の [BGM] の合図まで鳴らし直さない */
export function videoAudio(s, work, now) {
  const before = s.audio;
  s.audio = cutForVideo(s.audio, work, s.slide, now);
  return s.audio === before ? [] : toApproved(s, [astate(s.audio, now)]);
}

/** 動画が最後まで流れ終わった: その枚の `[BGM after video]` を鳴らす合図（鳴らすものがあったときだけ） */
export function videoEndAudio(s, work, idOf, now) {
  const before = s.audio;
  s.audio = afterVideo(s.audio, work, s.slide, idOf, now);
  return s.audio === before ? [] : toApproved(s, [astate(s.audio, now)]);
}

/** 語り手が話し始めた／話し終えた（T3）。聞き手の端末は、話しているあいだ自分で鳴らしている BGM を下げる。声の大きさそのものは送らない */
export function talkMessage(s, on) {
  s.talking = !!on;
  return approvedPeers(s).map((p) => ({ to: p.id, msg: { t: 'talk', on: !!on } }));
}

/** 再生中に間をおいて BGM の位置を配る（ずれた端末が合わせる） */
export function audioTick(s, now) {
  return s.audio.started && s.audio.id ? toApproved(s, [astate(s.audio, now)]) : [];
}

/** 語り手の再生の操作。承認済みの端末にだけ合図を送る */
export function playVideo(s, action, opts) {
  s.playback = command(s.playback, action, opts);
  const msg = vstate(s.playback, opts.now);
  return approvedPeers(s).map((p) => ({ to: p.id, msg }));
}

export function reject(s, id) {
  const p = s.peers.get(id);
  if (!p || p.status !== 'pending') return [];
  p.status = 'rejected';
  return [{ to: id, msg: { t: 'reject' } }];
}

export function onGot(s, id, n) {
  const p = s.peers.get(id);
  if (p && p.status === 'approved' && Number.isInteger(n)) p.received += 1;
}

/** 聞き手の画面の報告（U3）。**承認済みの端末のものだけ**受け、札に出す分を p.view に残す（R7）。
 *  受けたら true（語り手は札を書き直す） */
export function onView(s, id, msg) {
  const p = s.peers.get(id);
  if (!p || p.status !== 'approved') return false;
  const v = cleanView(msg);
  if (!v) return false;
  p.view = v;
  return true;
}

/** 音の点呼の返事。承認済みの端末のものだけ受ける（R7）。形が違えば level は null */
export function onHeard(s, id, msg) {
  const p = s.peers.get(id);
  if (!p || p.status !== 'approved' || !msg) return null;
  const level = Number.isFinite(msg.level) ? Math.max(0, Math.min(120, msg.level)) : null;
  return { round: Number(msg.round) || 0, level };
}

export function onGone(s, id) {
  s.peers.delete(id);
}

/** 枚を動かす。承認済みの端末にだけ知らせる。 */
export function goTo(s, n, total) {
  const next = Math.min(Math.max(1, n | 0), total);
  if (next === s.slide) return [];
  s.slide = next;
  return approvedPeers(s).map((p) => ({ to: p.id, msg: { t: 'slide', n: next } }));
}
