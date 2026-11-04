// 聞き手の画面。合言葉でつなぎ、承認を待ち、絵と動画を受け取り、合図どおりに出す。台本は受け取らない。
// 動画（段階2）: 荷物用の2本目の接続で受け取り、4MB の区切りごとに端末へ書く。再生は語り手の合図で自分の動画を動かす。
// 保存できない端末は、語り手の映像をそのまま受ける（予備の「その場で流す」）。
import './https.js';
import { t, applyI18n } from './i18n.js';
import { PROTOCOL } from './protocol.js';
import { ID_PREFIX, isCode, joinPeer, keepSignaling, keepAwake, deviceKind, iceState, iceLine, relayOffered, relayPaused } from './net.js';
import { whyBlocked, isAndroid, relayNote } from './ice.js';
import { SEGMENT, segmentReady, fmtMB } from './transfer.js';
import { apply } from './playback.js';
import { openStore, freeSpace } from './store.js';
import { createEngine } from './engine.js';
import { makeView, viewChanged } from './view.js';
import { beep, measure } from './tone.js';

applyI18n();
const $ = (id) => document.getElementById(id);

const pics = new Map();   // 番号 → object URL
let count = 0;
let expectedPics = 0;
let slide = 1;
let peer = null;
let slowTimer = 0;
let ended = false;     // 自分で閉じた（断られた・つなぎ直す）。PeerJS は破棄の印を付ける前に接続を閉じるので、自前で覚える

// 動画
// 試験用: ?nostore で保存を使わない（予備の「その場で流す」を確かめるため）
const NO_STORE = new URLSearchParams(location.search).has('nostore');
let store;                // undefined＝まだ開いていない / null＝使えない
const vids = new Map();   // id → { id, n, size, mime, mode, bytes, url }
let recv = null;          // 受け取り中: { id, offset, size, chunks, n }
let writing = Promise.resolve();
let lastV = null;         // 最後に届いた再生の合図
let remote = null;        // 予備で受けている映像 { stream, id }
let main = null;          // 語り手との合図用の接続
let narrator = '';        // 語り手の peer ID
let prepared = false;     // 動画の申告を済ませたか
const vEl = $('lvideo');
// 音（段階4）
const engine = createEngine();
let lastA = null;         // 最後に届いた BGM の合図
const TEST = new URLSearchParams(location.search).has('test');
// 語り手への画面の報告（語り手の画面の作り直し U3）
let welcomed = false;     // 承認された（welcome を受けた）。承認前は報告しない
let lastView = null;      // 最後に送った報告
// 声（段階3）。マイクを入れる・切るのはこの端末の人だけ（V4）。語り手は届けるかどうかを自分の側で決める（V5）
let micStream = null;     // マイクの流れ（エコー除去・雑音抑制つき）
let micState = 'none';    // 'on' | 'off' | 'listen' | 'denied' | 'none'
let vctx = null;          // 確かめの音・無音の代わりの流れに使う AudioContext
let sender = null;        // 声の通話の送り口（あとからマイクに差し替える）
let silent = null;        // マイクが無いときに声の通話へ流す無音
const voiceEl = $('voice');
let picSlides = new Set(); // 絵のある枚（welcome の pictures）。絵の無い枚（動画だけの枚）は、絵が無いのが正しい

/** その上演のあいだの合い札（途中復帰 P10）。合言葉ごとに、**この端末のブラウザ**に置く（localStorage）。
 *  語り手が承認した端末の合い札だけが、次から承認なしで通る（語り手のメモリにしか無い——別の上演では使えない）。
 *  ⚠️ 一度 sessionStorage（タブごと）にしたが、スマートフォンで入り直すと新しいタブになり（QR コードから開き直す・
 *     ブラウザがタブを閉じる）、合い札が消えて「入れる／断る」が出た（2026-10-24 実機）。同じブラウザの別のタブが
 *     同じ合い札で通るのは、同じ端末なので害が無い（R7 が守るのは、知らない端末） */
function tokenFor(code) {
  const key = 'dk-token-' + code;
  try {
    const have = localStorage.getItem(key);
    if (have && have.length >= 32) return have;
  } catch { /* 保存できない端末 */ }
  const a = new Uint8Array(16);
  crypto.getRandomValues(a);
  const tok = [...a].map((b) => b.toString(16).padStart(2, '0')).join('');
  try { localStorage.setItem(key, tok); } catch { /* 同上（この接続のあいだだけ有効） */ }
  return tok;
}
let token = '';

const fromHash = location.hash.replace('#', '').replace(/\D/g, '');
if (isCode(fromHash)) $('code').value = fromHash;
try { $('name').value = localStorage.getItem('dk-name') || ''; } catch { /* 保存できない端末 */ }

function status(text, actions = false) {
  $('status').textContent = text;
  $('retry').hidden = !actions;
}

$('joinForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const code = $('code').value.replace(/\D/g, '');
  if (!isCode(code)) { $('code').focus(); return; }
  try { localStorage.setItem('dk-name', $('name').value.trim()); } catch { /* 同上 */ }
  history.replaceState(null, '', '#' + code);
  keepAwake();
  engine.unlock(); // 「入る」を押した操作の中で、音を出せるようにしておく（P8）
  openVctx();
  const use = (document.querySelector('input[name=mic]:checked') || {}).value !== 'listen';
  if (use) await getMic(); else micState = 'listen';
  connect(code);
});

// ---------- 声（段階3 V2〜V4） ----------

function openVctx() {
  if (vctx) { vctx.resume().catch(() => {}); return; }
  try { const AC = window.AudioContext || window.webkitAudioContext; vctx = new AC(); } catch { vctx = null; }
}

/** マイクをもらう。許可されなければ 'denied'、マイクが無ければ 'none'（聞くことはそのままできる） */
async function getMic() {
  try {
    micStream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    micState = 'on';
  } catch (err) {
    micStream = null;
    micState = err && err.name === 'NotAllowedError' ? 'denied' : 'none';
  }
  renderMic();
  return !!micStream;
}

/** 声の通話に流す音: マイク（切っているときは止めた音）か、マイクが無ければ無音 */
function outgoingTrack() {
  if (micStream) return micStream.getAudioTracks()[0];
  if (!silent && vctx) silent = vctx.createMediaStreamDestination().stream.getAudioTracks()[0];
  return silent;
}

/** 語り手からの声の通話に答える（承認されたときに語り手が張る）。受けた声は <audio> で鳴らす——
 *  ブラウザのエコー除去が、この端末から出た声をこの端末のマイクから消せるように（Web Audio に通さない。V3） */
function answerVoice(call) {
  const tr = outgoingTrack();
  call.answer(tr ? new MediaStream([tr]) : undefined);
  call.on('stream', (stream) => { voiceEl.srcObject = stream; voiceEl.play().catch(() => {}); });
  call.on('close', () => { if (voiceEl.srcObject) voiceEl.srcObject = null; sender = null; });
  const pc = call.peerConnection;
  const findSender = () => { sender = pc ? pc.getSenders().find((s) => s.track && s.track.kind === 'audio') || pc.getSenders()[0] || null : null; };
  findSender();
  if (pc) pc.addEventListener('connectionstatechange', findSender);
}

function renderMic() {
  const b = $('micBtn');
  b.textContent = micState === 'on' ? t('micOn') : micState === 'off' ? t('micOff') : t('micStart');
  b.className = micState === 'on' ? 'on' : '';
  if (welcomed) report();
}

$('micBtn').addEventListener('click', async (e) => {
  e.stopPropagation(); // 画面のタップ（全画面）にしない
  if (micState === 'on' || micState === 'off') {
    micState = micState === 'on' ? 'off' : 'on';
    for (const tr of micStream.getAudioTracks()) tr.enabled = micState === 'on';
  } else if (await getMic()) {
    // 聞くだけから使うへ: 通話を張り直さずに、送り口の音をマイクに差し替える（PeerJS は通話の張り直しの取り決めを持たない）
    if (sender) await sender.replaceTrack(micStream.getAudioTracks()[0]).catch((err) => console.error(err));
  }
  renderMic();
});

const VOICE_NOTE = { video: 'voiceVideo', bgm: 'voiceBgm', held: 'voiceHeld', 'same-room': 'voiceSameRoom' };
function voiceNote(msg) {
  $('voiceNote').textContent = msg.heard ? (micState === 'on' ? t('voiceOnAir') : '') : VOICE_NOTE[msg.reason] ? t(VOICE_NOTE[msg.reason]) : '';
  quiet = !!msg.quiet;
  if (quiet) quietSeen = true;
  renderQuiet();
}

// 語り手の声を、この端末で鳴らすか（音の点呼が「語り手と同じ部屋」と見たら鳴らさない）。
// 部屋を移ったことを知っているのは本人だけなので、本人も戻せる。一度も止められていない端末にはボタンを出さない
let quiet = false;
let quietSeen = false;
function renderQuiet() {
  $('quietNote').hidden = !quiet;
  $('quietNote').textContent = quiet ? t('quietNote') : '';
  $('quietBtn').hidden = !quietSeen;
  $('quietBtn').textContent = quiet ? t('quietOn') : t('quietOff');
}
$('quietBtn').addEventListener('click', (e) => {
  e.stopPropagation(); // 画面のタップ（全画面）にしない
  if (main && main.open) main.send({ t: 'quiet', on: !quiet });
});

/** 音の点呼: ms のあいだマイクの音を測って返す。測るときはエコー除去・雑音抑制を切ったマイクを取り直す（一定の高さの音を消さないように） */
async function listenFor(conn, msg) {
  let level = null;
  if (TEST && window.__dkl.fakeHeard != null) level = window.__dkl.fakeHeard; // 自動テスト用（空気を通る音は1台の PC では作れない）
  else if (micState === 'on' || micState === 'off') {
    let raw = null;
    try { raw = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } }); } catch { raw = null; }
    openVctx();
    level = raw && vctx ? await measure(vctx, raw, Math.min(5000, Number(msg.ms) || 1000)) : null;
    if (raw) for (const tr of raw.getTracks()) tr.stop();
  }
  if (conn.open) conn.send({ t: 'heard', round: msg.round, level });
}

$('retry').addEventListener('click', (e) => { e.stopPropagation(); connect($('code').value.replace(/\D/g, '')); });

async function connect(code) {
  $('join').hidden = true;
  $('stage').hidden = false;
  status(t('connecting'));
  clearTimeout(slowTimer);
  // 中継があれば別々のネットワークでもつながるので、「同じ Wi-Fi ですか？」は中継が無いときだけ聞く
  // 中継の枠を使い切って止めているときは、その理由を「同じ Wi-Fi ですか？」の前に添える（損失の天井）
  slowTimer = setTimeout(() => {
    const note = relayNote(relayPaused(), 'listener');
    status(relayOffered() ? t('slowRelay') : (note ? `${t(note)} ${t('slow')}` : t('slow')), true);
  }, 15000);
  $('diag').textContent = '';
  if (peer) { ended = true; peer.destroy(); }
  ended = false;
  resetVideos();
  $('recBadge').hidden = true; // 録画中かは、承認のときに語り手が改めて知らせる
  $('clearVideos').hidden = true; // つないでいるあいだ（上演中）は出さない
  try {
    peer = await joinPeer();
  } catch (err) {
    return fail(t('signalError'));
  }
  keepSignaling(peer);
  peer.on('error', (err) => { if (err.type === 'peer-unavailable') fail(t('noRoom')); });
  const narratorId = ID_PREFIX + code;
  // 予備の「その場で流す」: 語り手からの映像だけ受ける
  peer.on('call', (call) => {
    if (call.peer !== narratorId) { call.close(); return; }
    if (call.metadata && call.metadata.kind === 'voice') { answerVoice(call); return; } // 声（段階3）
    call.answer();
    call.on('stream', (stream) => { remote = { stream, id: call.metadata && call.metadata.video }; refreshVideo(); });
    call.on('close', () => { if (remote && vEl.srcObject === remote.stream) vEl.srcObject = null; remote = null; refreshVideo(); });
  });
  // 端末の種類は語り手の「つなぎかけ」の案内にだけ使う（自己申告。守りには使わない）
  const conn = peer.connect(narratorId, { reliable: true, metadata: { device: deviceKind() } });
  main = conn;
  narrator = narratorId;
  token = tokenFor(code);
  prepared = false;
  welcomed = false;
  lastView = null;
  conn.on('open', () => {
    conn.send({ t: 'hello', v: PROTOCOL, name: $('name').value.trim(), device: deviceKind(), token });
    if (engine.unlocked) conn.send({ t: 'unlocked' });
  });
  conn.on('data', (msg) => handle(conn, msg, narratorId));
  // つながるまで ICE の様子を小さく出す（原因を絞るため。つながったら消す）。
  // 確認の通信に返事が1つも無ければ、どこで止まっているかを案内する（ice.js の whyBlocked）。
  // 中継が無く Android なら Chrome のローカル ネットワーク権限。中継が無く Android 以外なら、15秒後の「同じ Wi-Fi ですか？」に任せる
  const hints = { 'local-net': 'androidLocalNet', 'no-relay-here': 'noRelayHere', 'no-relay-there': 'noRelayThere' };
  let hinted = false;
  const diag = setInterval(async () => {
    if (conn.open || ended) { clearInterval(diag); $('diag').textContent = ''; return; }
    const s = await iceState(conn);
    $('diag').textContent = iceLine(s);
    const key = hints[whyBlocked(s, { relay: relayOffered(), android: isAndroid(deviceKind()) })];
    if (!hinted && key) {
      hinted = true;
      clearTimeout(slowTimer);
      status(t(key), true);
    }
  }, 2000);
  conn.on('close', () => lost(conn, t('lost')));
  // ⚠️ 語り手がタブを閉じても、PeerJS は接続の終わりを知らせないことがある（2026-10-24 実測: 2分たっても気づかなかった）。
  //    語り手の「終わり」（bye）が届かなかったときの予備として、接続の状態を見張る
  conn.on('open', () => {
    const pc = conn.peerConnection;
    if (!pc) return;
    let timer = 0;
    pc.addEventListener('iceconnectionstatechange', () => {
      const s = pc.iceConnectionState;
      clearTimeout(timer);
      if (s === 'failed' || s === 'closed') lost(conn, t('lost'));
      else if (s === 'disconnected') timer = setTimeout(() => { if (pc.iceConnectionState === 'disconnected') lost(conn, t('lost')); }, 8000);
    });
  });
}

/** 語り手との接続が終わった（切れた・上演が終わった）。同じ接続について1回だけ */
function lost(conn, text) {
  if (ended || conn !== main || conn.dkLost) return;
  conn.dkLost = true;
  fail(text);
  $('recBadge').hidden = true; // 切れたあとの声と画面は録られない
  // 「受け取った動画を消す」は、語り手との接続が終わってから（＝上演が終わって語り手が画面を閉じたら）だけ出す。
  // ⚠️ 受け取りが済んだら出す作りだと、上演中ずっと聞き手の画面に出ていた（2026-10-24 の指摘）
  $('clearVideos').hidden = !store;
}

function fail(text) {
  clearTimeout(slowTimer);
  status(text, true);
}

function handle(conn, msg, narratorId) {
  if (!msg || typeof msg !== 'object') return;
  clearTimeout(slowTimer);
  switch (msg.t) {
    case 'wait':
      status(t('waiting'));
      break;
    case 'volume':
      // 当日の音量つまみ（L5）。⚠️ iPhone の Safari は動画の音量（volume）を無視する——家族に iPhone は無い（2026-10-24）
      engine.setMusic(Number(msg.music));
      vEl.volume = Math.min(1, Math.max(0, Number(msg.video)));
      break;
    case 'bye':
      lost(conn, t('showEnded'));
      break;
    case 'voice':
      voiceNote(msg);
      break;
    case 'rec':
      $('recBadge').hidden = !msg.on; // 語り手が録画している（G4）
      break;
    case 'listen':
      listenFor(conn, msg);
      break;
    case 'tone':
      openVctx();
      if (vctx) beep(vctx);
      break;
    case 'reject':
      status(t('refused'));
      ended = true;
      peer.destroy();
      break;
    case 'welcome':
      document.title = msg.title;
      expectedPics = Array.isArray(msg.pictures) ? msg.pictures.length : 0;
      picSlides = new Set((Array.isArray(msg.pictures) ? msg.pictures : []).map((p) => p.n));
      for (const a of Array.isArray(msg.audio) ? msg.audio : []) {
        vids.set(String(a.id), { id: String(a.id), kind: 'audio', size: Number(a.size) || 0, mime: String(a.mime || 'audio/mpeg'), mode: null, bytes: 0, url: null });
      }
      for (const v of Array.isArray(msg.videos) ? msg.videos : []) {
        vids.set(String(v.id), { id: String(v.id), kind: 'video', n: v.n, size: Number(v.size) || 0, mime: String(v.mime || 'video/mp4'), mode: null, bytes: 0, url: null });
      }
      $('tapSound').hidden = engine.unlocked || ![...vids.values()].some((v) => v.kind === 'audio');
      welcomed = true;
      $('micBox').hidden = false;
      renderMic();
      lastView = null; // 承認し直した（入り直した）ときは、語り手の記録が新しいので必ず送る
      showStatus();
      maybePrepare();
      break;
    case 'pic': {
      if (!Number.isInteger(msg.n) || !msg.data) break;
      const old = pics.get(msg.n);
      if (old) URL.revokeObjectURL(old);
      pics.set(msg.n, URL.createObjectURL(new Blob([msg.data], { type: String(msg.mime || '') })));
      count = pics.size;
      conn.send({ t: 'got', n: msg.n });
      showStatus();
      if (msg.n === slide) show();
      maybePrepare();
      break;
    }
    case 'slide':
      if (Number.isInteger(msg.n)) { slide = msg.n; show(); }
      break;
    case 'vmode': {
      const v = vids.get(String(msg.id));
      if (v) v.mode = msg.mode === 'stored' ? 'stored' : 'stream';
      showStatus();
      break;
    }
    case 'vstate':
      lastV = { id: msg.id ? String(msg.id) : null, playing: !!msg.playing, pos: Number(msg.pos) || 0, at: performance.now() };
      engine.duck(!!(lastV.id && lastV.playing)); // 動画のあいだは BGM を下げる（P5）
      refreshVideo();
      break;
    case 'talk':
      engine.talk(!!msg.on); // 語り手が話しているあいだ BGM を下げる（plans/kamishibai-player-talk-duck.md の T3）
      break;
    case 'astate':
      lastA = { id: msg.id ? String(msg.id) : null, loop: msg.loop !== false, playing: !!msg.playing, pos: Number(msg.pos) || 0, at: performance.now() };
      refreshAudio();
      break;
    case 'sound': {
      const v = vids.get(String(msg.id));
      if (v && v.url) engine.playSound(v.url);
      break;
    }
  }
}

function show() {
  const u = pics.get(slide);
  const img = $('picture');
  if (u && vEl.hidden) { img.src = u; img.hidden = false; $('hint').hidden = !!document.fullscreenElement; }
  else if (!u) img.hidden = true;
  showPoster();
  report();
}

/** 絵の無い動画の枚（動画だけの枚）は、再生前にその枚の1本目の最初のコマを出す（work-format §2.4・2026-10-25 D4）。
 *  保存済みの動画がある端末だけ。まだ届いていない・「その場で流す」の端末は黒のまま */
function showPoster() {
  const el = $('lposter');
  const v = !picSlides.has(slide) && vEl.hidden
    ? [...vids.values()].find((x) => x.kind === 'video' && x.n === slide && x.url) : null;
  if (!v) {
    if (!el.hidden) { el.hidden = true; el.removeAttribute('src'); el.dataset.src = ''; }
    return;
  }
  if (el.dataset.src !== v.url) { el.src = v.url; el.dataset.src = v.url; }
  el.hidden = false;
}
// 止めたままでも最初のコマを描かせる（Safari は頭出しをしないと描かない）
$('lposter').addEventListener('loadedmetadata', () => { $('lposter').currentTime = 0.001; });

/** いま自分の画面に出しているものを語り手へ報告する（U3）。画面が変わったときだけ送る。
 *  ⚠️ 中身は状態の名前と数だけ。画面を映像で送り返すと回線と電池を食い、子供の端末の画面を語り手が覗く形にもなる */
function report() {
  if (!welcomed || !main || !main.open) return;
  const playingVideo = !vEl.hidden && (vEl.dataset.src || vEl.srcObject);
  const media = [...vids.values()].filter((v) => v.mode !== 'stream' && store);
  const hasAudio = [...vids.values()].some((v) => v.kind === 'audio');
  // 保存できない端末（store＝null）・音を「その場で流す」に回された端末は鳴らない。保存先を開く前（undefined）は鳴る見込みとして扱う
  const audioOk = hasAudio && store !== null && [...vids.values()].some((v) => v.kind === 'audio' && v.mode !== 'stream');
  const msg = makeView({
    slide,
    // 絵の無い枚（動画だけの枚）で再生前に黒い画面なのは、届いていないのではなく、それが正しい見え方（札を色つきにしない）。
    // 保存済みの動画がある端末は最初のコマを出す（showPoster）。届いていない端末は黒で、それも正しい見え方
    picture: (!$('picture').hidden && pics.has(slide)) || !picSlides.has(slide),
    video: playingVideo ? { local: !!vEl.dataset.src && !vEl.srcObject, stream: !!vEl.srcObject, playing: !vEl.paused } : null,
    waiting: !!(lastV && lastV.id) && !playingVideo,
    sound: !audioOk ? 'none' : engine.unlocked ? 'on' : 'tap',
    mic: micState,
    recv: { got: media.reduce((a, v) => a + Math.min(v.bytes, v.size), 0), all: media.reduce((a, v) => a + v.size, 0) },
  });
  if (!viewChanged(lastView, msg)) return;
  lastView = msg;
  main.send(msg);
}

/** 受け取りの様子を1行で（絵 → 動画の順） */
function showStatus() {
  report();
  if (count < expectedPics) return status(t('receiving', count, expectedPics));
  const pending = [...vids.values()].filter((v) => v.mode !== 'stream' && v.bytes < v.size && store);
  if (pending.length) {
    const got = pending.reduce((a, v) => a + v.bytes, 0);
    const all = pending.reduce((a, v) => a + v.size, 0);
    return status(t(pending.some((v) => v.kind === 'audio') ? 'receivingAudio' : 'receivingVideo', fmtMB(got), fmtMB(all)));
  }
  status('');
}

// ---------- 動画を受け取る（設計 #1〜#5） ----------

function resetVideos() {
  for (const v of vids.values()) if (v.url) URL.revokeObjectURL(v.url);
  vids.clear();
  recv = null;
  lastV = null;
  lastA = null;
  engine.setBgm(null, () => null);
  remote = null;
  vEl.pause();
  vEl.removeAttribute('src');
  vEl.srcObject = null;
  vEl.hidden = true;
  showPoster();
}

/** 動画は、絵を全部受け取ってから始める。
 *  ⚠️ PeerJS は接続ごとに別の WebRTC 接続を張るので、荷物用の接続が回線を占めると、合図用の接続の絵が止まる
 *  （2026-10-24 実測: 動画の受け取り中、絵が 5/18 のまま止まった）。絵が先に揃えば、待つあいだも上演は始められる */
function maybePrepare() {
  if (prepared || !vids.size || count < expectedPics || !main) return;
  prepared = true;
  prepareVideos(main, narrator);
}

async function prepareVideos(conn, narratorId) {
  if (store === undefined) store = NO_STORE ? null : await openStore();
  const free = store ? await freeSpace() : 0;
  const items = [];
  for (const v of vids.values()) {
    v.bytes = store ? await store.bytes(v.id) : 0;
    if (v.bytes >= v.size) await finish(v);
    items.push({ id: v.id, bytes: v.bytes });
  }
  // 入り直したときは持っている分を申告する——語り手はその続きから送る（承認はやり直すが、データはやり直さない）
  conn.send({ t: 'have', store: store ? store.kind : null, free: Number.isFinite(free) ? free : null, items });
  showStatus();
  if (!store || [...vids.values()].every((v) => v.bytes >= v.size)) return;
  const bulk = peer.connect(narratorId, { label: 'bulk', serialization: 'raw', reliable: true });
  bulk.on('data', (data) => onBulk(conn, data));
}

function onBulk(conn, data) {
  if (typeof data === 'string') {
    let m;
    try { m = JSON.parse(data); } catch { return; }
    if (m.t === 'begin' && vids.has(m.id)) {
      recv = { id: m.id, offset: Number(m.from) || 0, size: Number(m.size) || 0, chunks: [], n: 0 };
    } else if (m.t === 'end' && recv && recv.n) {
      flush(conn);
    }
    return;
  }
  if (!recv || !(data instanceof ArrayBuffer)) return;
  recv.chunks.push(data);
  recv.n += data.byteLength;
  if (segmentReady(recv.n, recv.offset, recv.size)) flush(conn);
}

/** 溜まった1区切りを端末へ書く。書けたら「ここまで書けた」と返す（語り手の送りすぎを止める窓になる） */
function flush(conn) {
  const r = recv;
  const v = vids.get(r.id);
  const blob = new Blob(r.chunks);
  const index = Math.floor(r.offset / SEGMENT);
  r.offset += r.n;
  r.chunks = [];
  r.n = 0;
  const upTo = r.offset;
  writing = writing.then(async () => {
    if (!v || v.mode === 'stream') return;
    await store.writeSegment(v.id, index, blob);
    v.bytes = upTo;
    if (conn.open) conn.send({ t: 'vgot', id: v.id, bytes: upTo });
    if (v.bytes >= v.size) await finish(v);
    showStatus();
  }).catch((err) => {
    console.error(err);
    if (v && v.mode !== 'stream') {
      v.mode = 'stream';
      if (conn.open) conn.send({ t: 'vfail', id: v.id });
    }
    showStatus();
  });
}

async function finish(v) {
  if (v.url) return;
  v.url = URL.createObjectURL(await store.blob(v.id, v.mime));
  if (v.kind === 'audio') {
    // いま鳴らすべき曲が届いたら、手元の合図は古いことがあるので位置を頼む（動画の sync と同じ）
    if (lastA && lastA.id === v.id && lastA.playing && main && main.open) main.send({ t: 'sync' });
    refreshAudio();
  } else refreshVideo();
}

// ---------- 音（段階4 P2〜P5・P8） ----------

function refreshAudio() {
  const m = lastA;
  if (!m) return;
  const now = m.playing ? { ...m, pos: m.pos + (performance.now() - m.at) / 1000 } : m;
  engine.setBgm(now, (id) => { const v = vids.get(id); return v && v.url ? v.url : null; });
}

/** 画面に触れたら音を出せるようにし、語り手に知らせる（語り手の画面の「音: 出せる」） */
async function unlockSound() {
  const was = engine.unlocked;
  const ok = await engine.unlock();
  $('tapSound').hidden = ok;
  if (ok && !was && main && main.open) main.send({ t: 'unlocked' });
  if (ok) refreshAudio();
  if (voiceEl.srcObject && voiceEl.paused) voiceEl.play().catch(() => {});
  report();
}
$('tapSound').addEventListener('click', (e) => { e.stopPropagation(); unlockSound(); });

// ---------- 再生（設計 #6・#7） ----------

function refreshVideo() {
  const m = lastV;
  if (!m || !m.id) {
    if (!vEl.hidden) { vEl.pause(); vEl.hidden = true; }
    $('tapPlay').hidden = true;
    show();
    showStatus();
    return;
  }
  const v = vids.get(m.id);
  const local = v && v.url;
  const stream = remote && remote.id === m.id ? remote.stream : null;
  if (!local && !stream) {
    // まだ届いていない（語り手が予備の映像をつなぐのを待つ）
    status(t('videoNotYet'));
    report();
    return;
  }
  vEl.hidden = false;
  $('picture').hidden = true;
  showPoster(); // 流し始めたら、最初のコマは下げる
  $('hint').hidden = true;
  $('clearVideos').hidden = true;
  if (local) {
    if (vEl.srcObject) vEl.srcObject = null;
    if (vEl.dataset.src !== v.url) {
      vEl.src = v.url;
      vEl.dataset.src = v.url;
      // 再生中に動画を開いた（途中から入った・入り直した）ら、いまの位置を頼む——手元の合図は古いことがある（onSync）
      if (m.playing && main && main.open) main.send({ t: 'sync' });
    }
    // 合図を受けてから動画の準備ができるまでの経過を足す（入り直した端末が、遅れた位置から始めないように）
    const now = m.playing ? { ...m, pos: m.pos + (performance.now() - m.at) / 1000 } : m;
    const a = apply({ pos: vEl.currentTime, paused: vEl.paused }, now);
    if (a.seek != null) vEl.currentTime = a.seek;
    if (a.play === true) tryPlay();
    if (a.play === false) vEl.pause();
  } else {
    if (vEl.srcObject !== stream) { vEl.removeAttribute('src'); vEl.dataset.src = ''; vEl.srcObject = stream; }
    tryPlay(); // 予備の映像は語り手の画面どおりに流れてくるので、止める・合わせるは要らない
  }
  status('');
  report();
}

// 再生が始まった（頭出しの読み込みが済んだ）ら、もう一度位置を合わせる。読み込みのあいだに語り手は先へ進んでいる。
// 2回目の頭出しは読み込み済みなので速い。ずれが1秒未満なら何もしないので、繰り返しにはならない
vEl.addEventListener('playing', () => { if (lastV && lastV.playing && vEl.src) refreshVideo(); });
vEl.addEventListener('play', report);
vEl.addEventListener('pause', report);

function tryPlay() {
  vEl.play().then(() => { $('tapPlay').hidden = true; }).catch(() => { $('tapPlay').hidden = false; });
}

// iPhone などは、画面をタップしたあとでないと音つきで再生できない
$('tapPlay').addEventListener('click', (e) => { e.stopPropagation(); tryPlay(); refreshVideo(); });

// 上演が終わったら消せる（r13。保存が日をまたいで残ることは当てにしない）
$('clearVideos').addEventListener('click', async (e) => {
  e.stopPropagation();
  if (!store) return;
  await store.clear();
  for (const v of vids.values()) { if (v.url) URL.revokeObjectURL(v.url); v.url = null; v.bytes = 0; }
  showPoster();
  $('clearVideos').hidden = true;
  status(t('videosCleared'));
});

// 絵をタップしたら全画面（iPhone の Safari は要素の全画面に対応しないので、何もしない）
$('stage').addEventListener('click', () => {
  unlockSound();
  if (document.fullscreenElement) document.exitFullscreen();
  else if (document.documentElement.requestFullscreen) document.documentElement.requestFullscreen().catch(() => {});
});
document.addEventListener('fullscreenchange', () => { $('hint').hidden = !!document.fullscreenElement || $('picture').hidden; });

// 自動テスト用（?test のときだけ）
if (TEST) window.__dkl = { audio: () => engine.state(), view: () => lastView, fakeHeard: null, voiceStream: () => voiceEl.srcObject };
