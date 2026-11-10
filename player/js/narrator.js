// 語り手の画面。作品を読み、受付を開き、承認し、枚を送る。動画は荷物用の接続で先に配り、合図で再生させる（段階2）。
// 画面は「準備・受付・上演」の3つを同じページの中で切り替える（語り手の画面の作り直し U1。ページを移ると接続が切れる）。
import './https.js';
import { t, applyI18n } from './i18n.js';
import { validateWork, fileMap, findWorkJson, dirEntries, workDirOf, resolvePictures, resolveVideos, resolveAudio, resolveBases, resolveCandidates, resolveLinks, videoId, uniqueById, seatAt, toSource } from './work.js';
import {
  createSession, onHello, approve, reject, onGot, onGone, goTo, approvedCount, wouldExceed,
  mayOpenBulk, onHave, onVideoFail, playVideo, onSync,
  knownToken, staleTwins, startShow, slideAudio, videoAudio, videoEndAudio, talkMessage, audioTick, setVolume, onView, onHeard, onLink, setRecording,
} from './protocol.js';
import { chipState, nextScreen, bannerFor, videosOn, pickVideo, mustStopFor, videoName, clampSplit, splitAt, SPLIT_DEFAULT, SPLIT_MIN, SPLIT_MAX, SPLIT_STEP } from './view.js';
import { createVoice, heardFrom, routes, voiceMessages, rollOrder, judgeRollCall } from './voice.js';
import { createMixer } from './mixer.js';
import { createRecorder } from './recorder.js';
import { pickMime, recordName, stageSource, createClock, clockStart, clockSlide, clockRead, isPractice, recordable } from './record.js';
import { beep, measure } from './tone.js';
import { CHUNK, mustWait, sendable, progress, fmtMB, fmtTime, picReady, nextPicture } from './transfer.js';
import { TICK_MS, vstate } from './playback.js';
import { astate, soundsAt, talkStep } from './audio.js';
import { createEngine } from './engine.js';
import {
  editable, sheetEnabled, mayReload, keepSlide, editorStep, boxFromFields, fieldsFromBox, boxText, paragraphs,
  emptySheet, setSlideEdits, removeItem, removeComment, isOldComment, judge, reconcile, applySheet, sheetMarkdown, sheetName,
  readSheet, storageKey, isEmpty, place, textOf, videoCueOf, pointSeat, clock as seatClock, mediaLines, isMedia, videoOf, markCut, setLinkVolume, linkVolumeNow, dbText,
  askPicture, choosePicture, sheetCounts, sheetGroups, workSig,
} from './corrections.js';
import {
  editOf, applyEdit, moveBy, resizeBy, nudge, resize, toIn, fromIn, sheetValues, KEYS as LAYOUT_KEYS, workPalette, meanLuma, contrast,
} from './layout.js';
import { boxElement } from './overlay-dom.js';
import { openRoom, keepSignaling, keepAwake, iceState, iceLine, relayOffered, relayPaused, routeState } from './net.js';
import { whyBlocked, isAndroid, relayNote } from './ice.js';
import qrcode from '../vendor/qrcode.mjs';
import { LinkPlayer, loadApi, MIN_VOLUME_DB } from './ytlink.js';
import { integratedLoudness, levelGain } from './loudness.js';

applyI18n();
const $ = (id) => document.getElementById(id);

let work = null;
let workMap = new Map();
let mediaMap = new Map();
let workDir = null;                // 作品フォルダそのもの（showDirectoryPicker で選べたときだけ）。修正票の保存先の最初の場所
let pictures = new Map();          // 番号 → { key, file, mime, size }
let videos = [];                   // [{ id, kind: 'video', n, key, file, size, mime, problem }]
let audios = [];                   // [{ id, kind: 'audio', key, file, size, mime, problem, gain? }]（BGM・効果音。段階4。gain＝大きすぎる BGM を下げる dB）
let links = [];                    // [{ id, kind: 'link', n, k, key, yt, start, end, captions, volume }]（リンクの動画。ファイルは無く、配らない）
const audioUrls = new Map();       // 音の id → 語り手の端末で鳴らす object URL
// 配る素材。**音を先に**（開演直後から要る。動画は枚に来るまで要らない＝P7）
const media = () => uniqueById([...audios, ...videos]); // 同じ動画を2つの枚で使っても、配るのは1回
const sendableMedia = () => media().filter((m) => !m.problem);
const idOf = (file) => { const a = audios.find((x) => x.key === file && !x.problem); return a ? a.id : null; };
const engine = createEngine();     // 語り手の端末でも鳴らす（P9）
const urls = new Map();            // 番号 → 語り手の画面に出す object URL
const bytes = new Map();           // 番号 → ArrayBuffer（一度だけ読む）
let session = createSession(1);
let peer = null;
const conns = new Map();           // 聞き手の peer ID → DataConnection（合図用）
const ways = new Map();            // 聞き手の peer ID → 道（'direct' | 'relay'）。語り手の札にだけ出す
const bulks = new Map();           // 聞き手の peer ID → DataConnection（荷物用。承認済みだけ）
const xfer = new Map();            // 聞き手の peer ID → Map(動画 id → { sent, acked, size, startedAt, startBytes, done })
const sending = new Set();         // 送り出し中の聞き手
const calls = new Map();           // 聞き手の peer ID → MediaConnection（予備の「その場で流す」）
const trying = new Map();          // つながりかけの接続（名乗る前）。原因を絞る表示用
let mic = null;                    // マイクの流れ（ローカル IP を隠させないために持っておく）
let openedAt = 0;                  // 受付を開いた時刻（待ち時間の記録）
let allReadyLogged = false;
let screen = 'prep';               // いまの画面（view.js の nextScreen が決める）
// 声（段階3）。語り手を真ん中にした星形: 聞き手ごとに声の通話を1本張り、この PC で混ぜて配る（V1）
const voice = createVoice();
const voiceCalls = new Map();      // 聞き手の peer ID → MediaConnection（声）
const voicePrev = new Map();       // 聞き手へ最後に知らせた「声が届いているか」
const joinedAt = new Map();        // 聞き手の peer ID → 入った順（音の点呼で「後から入ったほう」を決める）
let joinSeq = 0;
let actx = null;                   // 声を混ぜる AudioContext（受付を開く操作の中で作る）
let mixer = null;
// 録画と練習（G1〜G5・P1〜P4）
let clock = createClock();         // 経過時間（画面に出すだけ。どこにも残さない＝P4）
let recorder = null;               // 録画中だけある
let recTaps = [];                  // 録画へつないだ音の取り出し口（止めるときに外す）
// 練習しながら直す（修正票。work-format §6・E1〜E10）。⚠️ work.json は書き換えない。聞き手へは何も送らない（R1）
let sheet = null;                  // 修正票（練習用の版のときだけ。ブラウザの中に保存する）
let editing = null;                // 直す欄を開いている枚（閉じていれば null）
let editBoxes = [];                // 直す欄の画面の文字: [{ removed, fields: [{ text, orig }] } | null（元から無い枠）]
// 絵の上で直す（overlay_layout）。⚠️ 下敷きと置き場所は語り手のこの画面だけが使う（R1・L8）
const baseUrls = new Map();        // 番号 → 文字の枠を抜いた下敷き（overlay_base）の object URL
let editLayout = [];               // 直す欄を開いている枚の枠ごとの { x, y, width, height（EMU）, size（pt） }
let laySel = -1;                   // 選んでいる枠（0 始まり。選んでいなければ -1）
const TEST = new URLSearchParams(location.search).has('test');
const recMime = typeof MediaRecorder !== 'undefined' ? pickMime((m) => MediaRecorder.isTypeSupported(m)) : null;

// ---------- 画面の切り替え（U1） ----------

function setScreen(next) {
  screen = next;
  $('screenPrep').hidden = screen !== 'prep';
  $('screenRoom').hidden = screen !== 'room';
  $('screenShow').hidden = screen !== 'show';
  for (const b of document.querySelectorAll('#tabs .tab')) {
    b.disabled = !work && b.dataset.screen !== 'prep';
    if (b.dataset.screen === screen) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
  }
  renderBanner();
  renderPractice();
  window.scrollTo(0, 0);
}

const go = (ev) => setScreen(nextScreen(screen, ev, { hasWork: !!work }));
for (const b of document.querySelectorAll('[data-screen], [data-goto]')) {
  b.addEventListener('click', () => go({ type: 'tab', to: b.dataset.screen || b.dataset.goto }));
}

// ---------- 作品を読む ----------

function entriesOf(input) {
  return [...input.files].map((file) => ({ path: file.webkitRelativePath || file.name, file }));
}

function takeEntries(input) {
  const entries = entriesOf(input);
  input.value = '';
  return entries;
}

/** 作品フォルダの選び方。showDirectoryPicker があればそれで選ぶ（フォルダそのものが手に入り、修正票の保存画面を作品フォルダで開ける。
 *  <input webkitdirectory> ではファイルしか受け取れず、保存画面がブラウザの前に使った場所で開いて、作品の外に保存された。2026-11-07 実機で）。
 *  無いブラウザ・キャンセルできない場面では、いままでどおり input の change で受け取る */
function pickFolder(input, open) {
  input.addEventListener('click', async (e) => {
    if (typeof window.showDirectoryPicker !== 'function') return;
    e.preventDefault();
    let dir;
    try {
      dir = await window.showDirectoryPicker({ id: 'dk-work' });
    } catch (err) {
      if (!(err && err.name === 'AbortError')) showLoadError([String((err && err.message) || err)]);
      return;
    }
    let entries;
    try {
      entries = await dirEntries(dir);
    } catch (err) {
      return showLoadError([String((err && err.message) || err)]);
    }
    await open(entries, dir);
  });
  input.addEventListener('change', (e) => open(takeEntries(e.target), null));
}

/** 選んだフォルダから work.json を読んで検査する → { work, map, dir } か、読めなければ null（理由は出す） */
async function readWorkFolder(entries, dir) {
  const found = findWorkJson(entries.map((x) => x.path));
  if (!found) { showLoadError([t('noWorkJson')]); return null; }
  let json;
  try {
    json = JSON.parse(await entries.find((x) => x.path.replace(/\\/g, '/') === found.path).file.text());
  } catch (err) {
    showLoadError([String(err.message || err)]);
    return null;
  }
  const { work: w, errors } = validateWork(json);
  if (errors.length) { showLoadError([t('badWork'), ...errors]); return null; }
  let d = null;
  if (dir) { try { d = await workDirOf(dir, found.base); } catch { d = null; } }
  return { work: w, map: fileMap(entries, found.base), dir: d };
}

pickFolder($('pickWork'), async (entries, dir) => {
  // 受付中に作品を選び直すと、聞き手へ配った絵・動画の一覧と食い違う（E10）
  if (peer) return showLoadError([t('workLocked')]);
  const r = await readWorkFolder(entries, dir);
  if (!r) return;
  closeEditor({ type: 'cancel' });
  work = r.work;
  workMap = r.map;
  workDir = r.dir;
  mediaMap = new Map();
  sheet = loadSheet(work);
  // 開いたときも、修正票を作品と照らし合わせる（反映済みは消す）。読み直すときだけだと、ページを開き直して選んだ作品に
  // 反映済みの件が残り、ボタンの数（未反映 0）と一覧が食い違った（2026-10-27）
  let msg = '';
  if (sheet && sheet.items.length) {
    const rv = resolveVideos(work, [workMap, mediaMap]);
    const rp = resolvePictures(work, [workMap, mediaMap]);
    const rc = reconcile(sheet, work, (x) => identOf(rv.videos, x, rp.pictures));
    if (rc.done || rc.resigned) { sheet = rc.sheet; saveSheet(); }
    if (rc.done) msg = t('opened', rc.done, sheet.items.length);
  }
  note2(msg);
  resolve();
});

// 作品を読み直す（E10）: 練習中だけ。今の画面にとどまり、今の枚を保つ。修正票を読み直した作品と比べる
pickFolder($('reloadWork'), async (entries, dir) => {
  if (!mayReload({ hasWork: !!work, roomOpen: !!peer })) return note2(t('workLocked'));
  const r = await readWorkFolder(entries, dir);
  if (!r) return setScreen('prep'); // 読めなかった理由は準備の画面に出ている（今の作品はそのまま）
  await reloadWith(r);
});

async function reloadWith(r) {
  if (!mayReload({ hasWork: !!work, roomOpen: !!peer })) return;
  closeEditor({ type: 'close' });
  closeCand();
  if (session.playback.id) stopVideo();
  chosenVideo = null;
  const oldTitle = work.title;
  work = r.work;
  workMap = r.map; // 素材フォルダを別に選んでいたら、それはそのまま使う
  workDir = r.dir;
  let msg = '';
  if (sheetEnabled(work)) {
    const rv = resolveVideos(work, [workMap, mediaMap]);
    const rp = resolvePictures(work, [workMap, mediaMap]);
    const rc = reconcile({ ...(sheet || loadSheet(work)), title: work.title }, work, (x) => identOf(rv.videos, x, rp.pictures));
    sheet = rc.sheet;
    if (oldTitle !== work.title) forgetSheet(oldTitle);
    saveSheet();
    msg = t('reloaded', rc.done, sheet.items.length);
  } else {
    sheet = null;
  }
  await resolve({ keep: keepSlide(session.slide, work.slides.length) });
  if (session.audio.started) { send(slideAudio(session, work, idOf, Date.now())); playHere(false); }
  renderSheet();
  note2(msg);
}

function note2(text) {
  $('reloadNote').hidden = !text;
  $('reloadNote').textContent = text;
}

$('pickMedia').addEventListener('change', (e) => {
  const entries = entriesOf(e.target);
  e.target.value = '';
  const top = entries.length ? entries[0].path.replace(/\\/g, '/').split('/')[0] : '';
  mediaMap = fileMap(entries, entries.length && entries[0].path.includes('/') ? top : '');
  resolve();
});

// ---------- BGM の曲の大きさをそろえる（docs/work-format.md §4。2026-11-09） ----------
// 見本の曲を自分の曲（CD・配信）に差し替えると、約20dB 大きく鳴って語りを消す。開演より前に測り、大きすぎる曲だけ下げる。
// 曲を丸ごと読み解くのは語り手の端末だけ（PC）。聞き手へは下げる量だけを welcome で渡す

const LEVEL_KEY = 'dk-level:';      // ＋曲の id → 測った大きさ（LUFS）。同じ曲は2回目から測らない

const gainOf = (id) => { const a = audios.find((x) => x.id === id); return a && a.gain ? a.gain : 0; };

async function loudnessOf(a) {
  try { const v = localStorage.getItem(LEVEL_KEY + a.id); if (v !== null) return Number(v); } catch { /* 覚えられないブラウザ */ }
  const AC = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  const buf = await new AC(1, 1, 44100).decodeAudioData(await a.file.arrayBuffer());
  const l = integratedLoudness(Array.from({ length: buf.numberOfChannels }, (_, i) => buf.getChannelData(i)), buf.sampleRate);
  try { localStorage.setItem(LEVEL_KEY + a.id, String(l)); } catch { /* 同上 */ }
  return l;
}

async function measureLevels() {
  const bgm = new Set(work.slides.flatMap((s) => s.cues.filter((c) => c.type === 'bgm').map((c) => c.file)));
  const songs = audios.filter((a) => bgm.has(a.key));
  const note = $('levelNote');
  note.hidden = !songs.length;
  note.textContent = t('levelMeasuring');
  for (const a of songs) {
    try { a.lufs = await loudnessOf(a); } catch { a.lufs = null; }   // 読み解けない曲はそのまま鳴らす
    a.gain = levelGain(a.lufs);
  }
  const low = songs.filter((a) => a.gain < 0);
  note.hidden = !low.length;
  note.replaceChildren();
  if (low.length) {
    const p = document.createElement('p');
    p.textContent = t('levelLowered');
    note.append(p, ul(low.map((a) => `${a.key} (${a.gain.toFixed(1).replace('-', '−')} dB)`)));
  }
}

async function resolve(opts = {}) {
  for (const u of urls.values()) URL.revokeObjectURL(u);
  urls.clear();
  bytes.clear();
  const r = resolvePictures(work, [workMap, mediaMap]);
  pictures = new Map([...r.pictures].map(([n, p]) => [n, { ...p, size: p.file.size }]));
  for (const [n, p] of pictures) urls.set(n, URL.createObjectURL(p.file));
  const rv = resolveVideos(work, [workMap, mediaMap]);
  videos = await Promise.all(rv.videos.map(async (v) => ({
    ...v, kind: 'video', id: await videoId(work.title, v.key, v.size, v.file.lastModified), problem: sendable(v),
  })));
  links = resolveLinks(work);
  // 埋め込みの API を先に読む。読めなければ準備の画面に出す（上演の枚に来てからでは、流せないと分かるのが遅い）
  $('linkWarn').hidden = true;
  if (links.length) loadApi().catch(() => { $('linkWarn').textContent = t('linkPrepNo'); $('linkWarn').hidden = false; renderLinkNote(); });
  for (const u of baseUrls.values()) URL.revokeObjectURL(u);
  baseUrls.clear();
  for (const [n, b] of resolveBases(work, [workMap, mediaMap])) baseUrls.set(n, URL.createObjectURL(b.file));
  const ra = resolveAudio(work, [workMap, mediaMap]);
  for (const u of audioUrls.values()) URL.revokeObjectURL(u);
  audioUrls.clear();
  audios = await Promise.all(ra.audio.map(async (a) => {
    const id = await videoId(work.title, a.key, a.size, a.file.lastModified);
    audioUrls.set(id, URL.createObjectURL(a.file));
    return { ...a, kind: 'audio', id, problem: sendable({ ...a, kind: 'audio' }) };
  }));
  await measureLevels();
  $('loadError').hidden = true;
  $('workTitle').textContent = work.title;
  const missing = [...r.missing, ...rv.missing, ...ra.missing];
  const miss = $('missing');
  miss.hidden = missing.length === 0;
  miss.replaceChildren();
  if (missing.length) {
    const p = document.createElement('p');
    p.textContent = t('missing', missing.length);
    miss.append(p, ul(missing));
  }
  const bad = media().filter((v) => v.problem);
  $('videoWarn').hidden = !bad.length;
  $('videoWarn').replaceChildren();
  if (bad.length) {
    const p = document.createElement('p');
    p.textContent = t('videoNotSent');
    $('videoWarn').append(p, ul(bad.map((v) => `${v.key} (${fmtMB(v.size)}) — ${t('why_' + v.problem)}`)));
  }
  $('mediaRow').hidden = missing.length === 0;
  $('prepNext').hidden = false;
  $('tabWork').textContent = work.title;
  $('draftBanner').hidden = !work.draft;
  if (opts.keep) {
    // 読み直し（E10）: 今の画面・今の枚のまま
    session.slide = opts.keep;
    renderSlide();
    setScreen(screen);
  } else {
    session.slide = 1;
    renderSlide();
    go({ type: 'loaded', missing: missing.length }); // 足りない素材が無ければ受付へ（あれば準備に残り、素材フォルダを選ばせる）
  }
  renderRec();
}

function showLoadError(lines) {
  const box = $('loadError');
  box.hidden = false;
  box.replaceChildren(...lines.map((l) => { const p = document.createElement('p'); p.textContent = l; return p; }));
}

// ---------- 受付 ----------

$('openRoom').addEventListener('click', async () => {
  // 本番（受付中）は直さない（E1）。開いている直す欄は、書きかけを修正票の下書きとして残して閉じる
  closeEditor({ type: 'room' });
  $('openRoom').disabled = true;
  $('roomStatus').textContent = t('opening');
  session.expected = Math.max(0, parseInt($('expected').value, 10) || 0);
  if (!mic) { mic = await getMic(); if (mic) for (const tr of mic.getAudioTracks()) tr.enabled = false; } // 声を出すのは「自分のマイク: 入」から
  renderMicPick();
  $('micWarn').hidden = !!mic;
  try {
    const room = await openRoom();
    peer = room.peer;
  } catch (err) {
    $('openRoom').disabled = false;
    $('roomStatus').textContent = t('signalError') + ` (${err.type || err.message})`;
    return;
  }
  keepSignaling(peer);
  keepAwake();
  startMixer();
  openedAt = Date.now();
  logWait(t('logOpened', work.title, fmtMB(sendableMedia().reduce((a, m) => a + m.size, 0))));
  const code = peer.id.slice(-6);
  const url = `${location.origin}${location.pathname.replace(/[^/]*$/, '')}listen.html#${code}`;
  $('roomStatus').textContent = '';
  $('code').textContent = code.replace(/(\d{3})(\d{3})/, '$1 $2');
  $('joinUrl').textContent = url;
  // 中継の枠を使い切っているなら、受付の下に出す（損失の天井。直接つながる端末だけで上演できる）
  const note = relayNote(relayPaused());
  $('relayNote').hidden = !note;
  $('relayNote').textContent = note ? t(note) : '';
  const qr = qrcode(0, 'M');
  qr.addData(url);
  qr.make();
  $('qr').innerHTML = qr.createSvgTag({ cellSize: 4, margin: 2 });
  $('expected').disabled = true;
  $('pickWork').disabled = true; // 受付中は作品を選び直せない・読み直せない（E10）
  renderEditTools();
  $('room').hidden = false;
  peer.on('connection', accept);
  renderPeers();
  renderPractice();
});

$('expected').addEventListener('input', () => { session.expected = Math.max(0, parseInt($('expected').value, 10) || 0); });

function accept(conn) {
  if (conn.label === 'bulk') return acceptBulk(conn);
  trying.set(conn.peer, conn);
  renderTrying();
  conn.on('open', () => { trying.delete(conn.peer); renderTrying(); });
  conn.on('data', (msg) => {
    if (!msg || typeof msg !== 'object') return;
    const id = conn.peer;
    if (msg.t === 'hello') {
      const old = conns.get(id);
      if (old && old !== conn) old.close();
      conns.set(id, conn);
      send(onHello(session, id, msg));
      // 途中復帰（P10）: この上演で承認した端末の合い札なら、承認なしで今の枚・曲・動画へ戻す
      if (knownToken(session, msg.token)) {
        // 入り直す前の古い接続を片付ける（同じ端末が2台並ばないように）
        for (const old of staleTwins(session, id, msg.token)) {
          if (joinedAt.has(old)) joinedAt.set(id, joinedAt.get(old)); // 入った順は入り直す前のまま
          const c = conns.get(old); forget(old); if (c) c.close();
        }
        logWait(t('logBack', who(session.peers.get(id))));
        admit(id);
      }
    } else if (msg.t === 'got') {
      onGot(session, id, msg.n);
    } else if (msg.t === 'have') {
      send(onHave(session, id, msg, media()));
      // 受け取り済みの動画もここで記録する（受け取り済みの端末は荷物用の接続を開かない。
      // 記録が無いと、入り直した端末を「まだ受け取っていない」と見て予備の映像を流してしまう）
      for (const item of session.peers.get(id).plan || []) {
        const v = media().find((x) => x.id === item.id);
        if (v && item.mode === 'stored') { const st = stateOf(id, v, item.from); if (st.done) maybeLogDone(id, v, st); }
      }
      startTransfers(id);
      if (session.playback.id) streamTo(id);
    } else if (msg.t === 'unlocked') {
      const p = session.peers.get(id);
      if (p) p.unlocked = true;
    } else if (msg.t === 'sync') {
      send(onSync(session, id, Date.now()));
    } else if (msg.t === 'vgot') {
      onVideoGot(id, msg);
    } else if (msg.t === 'vfail') {
      send(onVideoFail(session, id, String(msg.id)));
      if (session.playback.id) streamTo(id);
    } else if (msg.t === 'view') {
      // 聞き手の画面の報告（U3）。承認済みの端末のものだけ札に出る（onView が捨てる）
      if (onView(session, id, msg)) { renderChips(); updateVoice(); }
      return;
    } else if (msg.t === 'quiet') {
      // 聞き手が自分の端末で語り手の声を鳴らす／鳴らさないを選んだ（別の部屋へ移った・戻った）。承認済みの端末だけ（R7）
      const p = session.peers.get(id);
      if (p && p.status === 'approved') { if (msg.on) voice.quiet.add(id); else voice.quiet.delete(id); updateVoice(); }
      return;
    } else if (msg.t === 'link') {
      // 聞き手の端末で、リンクの動画を流せるか（埋め込みを禁じられた・ネットに出られない）
      if (onLink(session, id, msg)) { renderLinkNote(); renderChips(); }
    } else if (msg.t === 'heard') {
      const h = onHeard(session, id, msg);
      if (h) gotHeard(id, h);
      return;
    }
    renderPeers();
  });
  conn.on('close', () => {
    trying.delete(conn.peer); renderTrying();
    if (conns.get(conn.peer) === conn) forget(conn.peer);
  });
}

function forget(id) {
  conns.delete(id);
  ways.delete(id);
  const b = bulks.get(id);
  if (b) { bulks.delete(id); b.close(); }
  const c = calls.get(id);
  if (c) { calls.delete(id); c.close(); }
  xfer.delete(id);
  sending.delete(id);
  picsToSend.delete(id);
  const vc = voiceCalls.get(id);
  if (vc) { voiceCalls.delete(id); vc.close(); }
  if (mixer) mixer.drop(id);
  voicePrev.delete(id);
  voice.held.delete(id);
  voice.sameRoom.delete(id);
  voice.quiet.delete(id);
  onGone(session, id);
  renderPeers();
  updateVoice();
}

// 荷物用の接続。承認済みの端末からだけ受ける（R7）
function acceptBulk(conn) {
  conn.on('open', () => {
    if (!mayOpenBulk(session, conn.peer)) { conn.close(); return; }
    const old = bulks.get(conn.peer);
    if (old && old !== conn) old.close();
    bulks.set(conn.peer, conn);
    startTransfers(conn.peer);
  });
  conn.on('close', () => { if (bulks.get(conn.peer) === conn) bulks.delete(conn.peer); });
}

// 合図は送る順番を崩さない（welcome → いまの枚 → …）。1本の列に並べる。
// ⚠️ 動画はこの列に入れない（荷物用の接続で別に送る＝合図が動画の後ろに並ばない）
// ⚠️ 絵もこの列で続けて送らない——後から送った枚の合図が、送り待ちの絵（実際の作品で約10MB）の後ろに並んだ（入り直した端末で 8.5秒。2026-10-25 D1）。
//    絵は聞き手ごとの送り出し係（pumpPictures）が、送り待ちが小さくなってから1枚ずつ送る
let queue = Promise.resolve();
function send(out) {
  queue = queue.then(() => {
    const kick = new Set();
    for (const { to, msg } of out) {
      const conn = conns.get(to);
      if (!conn || !conn.open) continue;
      if (msg.t === 'pic') {
        if (!pictures.has(msg.n)) continue;
        if (!picsToSend.has(to)) picsToSend.set(to, new Set());
        picsToSend.get(to).add(msg.n);
        kick.add(to);
      } else if (msg.t === 'vstate' && msg.id && msg.id === session.playback.id) {
        // 再生の位置は、列に並んだときではなく送り出す瞬間の値にする
        conn.send(vstate(session.playback, Date.now()));
      } else {
        conn.send(msg);
      }
    }
    for (const id of kick) pumpPictures(id);
  }).catch((err) => console.error(err));
}

// ---------- 絵の送り出し（2026-10-25 D1・D2） ----------

const picsToSend = new Map();      // 聞き手の peer ID → 送り待ちの絵の番号（Set）
const pumping = new Set();         // 送り出し中の聞き手

/** 聞き手1人ぶんの絵を、送り待ちが小さくなってから1枚ずつ送る。次の1枚は送るたびに「いまの枚」から選び直す（D2） */
async function pumpPictures(id) {
  if (pumping.has(id)) return;
  pumping.add(id);
  try {
    for (;;) {
      const pending = picsToSend.get(id);
      const conn = conns.get(id);
      if (!pending || !pending.size || !conn || !conn.open) return;
      while (!picReady(conn.dataChannel ? conn.dataChannel.bufferedAmount : 0, conn.bufferSize)) {
        await sleep(20);
        if (conns.get(id) !== conn || !conn.open) return;
      }
      const n = nextPicture(pending, session.slide);
      pending.delete(n);
      const p = pictures.get(n);
      if (!p) continue;
      if (!bytes.has(n)) bytes.set(n, await p.file.arrayBuffer());
      if (conns.get(id) !== conn || !conn.open) return;
      conn.send({ t: 'pic', n, mime: p.mime, data: bytes.get(n) });
    }
  } catch (err) {
    console.error(err);
  } finally {
    pumping.delete(id);
  }
}

// ---------- 動画を配る（設計 #1〜#5） ----------

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const READ = 16 * CHUNK; // 1MB ずつファイルから読み、64KB に分けて送る

async function startTransfers(id) {
  const p = session.peers.get(id);
  const conn = bulks.get(id);
  if (!p || !p.plan || !conn || !conn.open || sending.has(id)) return;
  sending.add(id);
  try {
    for (const item of p.plan) {
      const v = media().find((x) => x.id === item.id);
      if (!v || item.mode !== 'stored') continue;
      const st = stateOf(id, v, item.from);
      if (st.done) { maybeLogDone(id, v, st); continue; }
      await sendVideo(conn, v, st, item);
      if (bulks.get(id) !== conn || !conn.open) return;
    }
  } catch (err) {
    console.error(err);
  } finally {
    sending.delete(id);
  }
}

function stateOf(id, v, from) {
  if (!xfer.has(id)) xfer.set(id, new Map());
  const m = xfer.get(id);
  if (!m.has(v.id)) {
    m.set(v.id, { sent: from, acked: from, size: v.size, startedAt: Date.now(), startBytes: from, done: from >= v.size, logged: false });
  }
  return m.get(v.id);
}

async function sendVideo(conn, v, st, item) {
  st.sent = st.acked; // 送り直すときは「書けた」ところから
  conn.send(JSON.stringify({ t: 'begin', id: v.id, from: st.sent, size: v.size }));
  while (st.sent < v.size) {
    if (!conn.open || item.mode !== 'stored') return;
    const block = await v.file.slice(st.sent, Math.min(st.sent + READ, v.size)).arrayBuffer();
    for (let off = 0; off < block.byteLength; off += CHUNK) {
      // 送り待ち（ブラウザの列と PeerJS の列）が多い・返事の来ていない分が窓を超えたら待つ
      while (mustWait(conn.dataChannel ? conn.dataChannel.bufferedAmount : 0, st.sent, st.acked) || conn.bufferSize > 0) {
        if (!conn.open || item.mode !== 'stored') return;
        await sleep(20);
      }
      if (!conn.open) return; // 聞き手が再読み込みした（切れた接続へ送り続けない）
      conn.send(block.slice(off, off + CHUNK));
      st.sent += Math.min(CHUNK, block.byteLength - off);
    }
  }
  conn.send(JSON.stringify({ t: 'end', id: v.id }));
}

function onVideoGot(id, msg) {
  const m = xfer.get(id);
  const st = m && m.get(String(msg.id));
  if (!st) return;
  st.acked = Math.max(st.acked, Number(msg.bytes) || 0);
  if (st.acked >= st.size) {
    st.done = true;
    maybeLogDone(id, media().find((v) => v.id === msg.id), st);
  }
}

// ---------- 待ち時間の記録（設計 #8） ----------

function logWait(line) {
  const now = new Date();
  const since = openedAt ? ` [+${fmtTime((now - openedAt) / 1000)}]` : '';
  $('waitLog').textContent += `${now.toTimeString().slice(0, 8)}${since} ${line}\n`;
  $('waitCard').hidden = false;
}

function maybeLogDone(id, v, st) {
  if (!v || st.logged) return;
  st.logged = true;
  const p = session.peers.get(id);
  if (v.kind === 'audio') {
    // 音は小さなファイルが何本もあるので、全部揃ったときに1行だけ書く
    const m = xfer.get(id) || new Map();
    const sts = audios.filter((a) => !a.problem).map((a) => m.get(a.id));
    if (p && !p.audioLogged && sts.every((x) => x && x.done)) {
      p.audioLogged = true;
      const t0 = Math.min(...sts.map((x) => x.startedAt));
      const got = sts.reduce((a, x) => a + x.size - x.startBytes, 0);
      const sec = (Date.now() - t0) / 1000;
      if (got > 0) logWait(t('logAudioDone', who(p), fmtMB(got), fmtTime(sec), (got / 1e6 / Math.max(sec, 0.001)).toFixed(1)));
    }
  } else if (st.size > st.startBytes) { // 入り直す前に受け取り済みだったもの（何も送っていない）は書かない
    const pr = progress(st.acked, st.size, st.startedAt, Date.now(), st.startBytes);
    logWait(t('logDone', who(p), fmtMB(st.size - st.startBytes), fmtTime((Date.now() - st.startedAt) / 1000), pr.mbps.toFixed(1)));
  }
  checkAllReady();
}

function checkAllReady() {
  const approved = [...session.peers.values()].filter((p) => p.status === 'approved');
  if (allReadyLogged || !approved.length || approved.length < session.expected) return;
  const ready = approved.every((p) => p.plan && p.plan.every((x) => x.mode === 'stream'
    || ((xfer.get(p.id) || new Map()).get(x.id) || {}).done));
  if (!ready) return;
  allReadyLogged = true;
  logWait(t('logAllReady', approved.length));
}

$('copyLog').addEventListener('click', () => {
  if (navigator.clipboard) navigator.clipboard.writeText($('waitLog').textContent).catch(() => {});
});

// ---------- 受付の一覧 ----------

function who(p) { return p ? `${p.name || t('unnamed')} — ${p.device}` : '?'; }

function audioLine(p) {
  if (!audios.length) return '';
  const unlocked = ` · ${p.unlocked ? t('soundOn') : t('soundTap')}`;
  if (!p.plan) return unlocked;
  const items = p.plan.filter((x) => audios.some((a) => a.id === x.id));
  if (items.some((x) => x.mode === 'stream')) return ` · ${t('audioNone')}${unlocked}`;
  const sts = items.map((x) => (xfer.get(p.id) || new Map()).get(x.id) || { acked: 0, size: 0, done: false });
  const size = audios.filter((a) => !a.problem).reduce((a, m) => a + m.size, 0);
  if (sts.every((x) => x.done)) return ` · ${t('audioReady', fmtMB(size))}${unlocked}`;
  return ` · ${t('audioProgress', fmtMB(sts.reduce((a, x) => a + x.acked, 0)), fmtMB(size))}${unlocked}`;
}

/** リンクの動画を流せない端末の理由（全部・'*'＝埋め込みそのもの）。流せるか分からないものは入れない */
function linkProblems(p, id = null) {
  const got = p.links || {};
  const why = new Set();
  if (got['*']) why.add(got['*']);
  for (const l of links) if ((!id || l.id === id) && got[l.id]) why.add(got[l.id]);
  return [...why];
}

function videoLine(p) {
  const bad = links.length ? linkProblems(p) : [];
  const link = bad.length ? ` · ${t('linkPeerNo', bad.map((w) => t('linkWhy_' + w)).join('、'))}` : '';
  return fileVideoLine(p) + link;
}

function fileVideoLine(p) {
  if (!p.plan) return videos.length ? ` · ${t('videoWaiting')}` : '';
  return p.plan.filter((x) => !audios.some((a) => a.id === x.id)).map((x) => {
    if (calls.has(p.id) && vCurrent && x.id === vCurrent.id) return ` · ${t('videoStreaming')}`;
    if (x.mode === 'stream') return ` · ${t('videoStream', t('why_' + x.reason))}`;
    const st = (xfer.get(p.id) || new Map()).get(x.id);
    if (!st) return ` · ${t('videoQueued')}`;
    if (st.done) return ` · ${t('videoReady', fmtMB(st.size))}`;
    const pr = progress(st.acked, st.size, st.startedAt, Date.now(), st.startBytes);
    return ` · ${t('videoProgress', fmtMB(st.acked), fmtMB(st.size), pr.mbps.toFixed(1), fmtTime(pr.eta))}`;
  }).join('');
}

let peersTimer = 0;
function renderPeers() {
  clearTimeout(peersTimer);
  const pending = [...session.peers.values()].filter((p) => p.status === 'pending');
  const approved = [...session.peers.values()].filter((p) => p.status === 'approved');
  $('count').textContent = t('approvedOf', approvedCount(session), session.expected);
  const pill = $('tabCount');
  pill.hidden = !peer;
  pill.textContent = t('tabCount', approvedCount(session), session.expected);
  pill.classList.toggle('warn', pending.length > 0);
  renderBanner();
  renderChips();

  const req = $('requests');
  req.replaceChildren();
  if (!pending.length) req.append(li(t('none'), 'muted'));
  for (const p of pending) req.append(requestItem(li('', wouldExceed(session) ? 'request over' : 'request'), p));

  const lis = $('listeners');
  lis.replaceChildren();
  if (!approved.length) lis.append(li(t('none'), 'muted'));
  for (const p of approved) {
    lis.append(li(`${who(p)}${wayLine(p)} · ${t('pictures', Math.min(p.received, pictures.size), pictures.size)}${audioLine(p)}${videoLine(p)}`));
  }
  // 受け取り中は1秒ごとに書き直す（速さ・残りの見込み）
  if (approved.some((p) => p.plan && p.plan.some((x) => x.mode === 'stored' && !((xfer.get(p.id) || new Map()).get(x.id) || {}).done))) {
    peersTimer = setTimeout(renderPeers, 1000);
  }
}

/** 承認の依頼1件（受付の一覧と、上演の画面の知らせの帯で同じものを使う） */
function requestItem(item, p) {
  const name = document.createElement('span');
  name.textContent = item.classList.contains('item') ? t('bannerJoin', who(p)) : who(p);
  const yes = button(t('let'), () => {
    allReadyLogged = false;
    admit(p.id);
    renderPeers();
  });
  const no = button(t('refuse'), () => {
    const conn = conns.get(p.id);
    send(reject(session, p.id));
    queue.then(() => setTimeout(() => conn && conn.close(), 500));
    renderPeers();
  });
  item.append(name, yes, no);
  if (wouldExceed(session)) {
    const warn = document.createElement('div');
    warn.className = 'warn';
    warn.textContent = t('over', approvedCount(session), session.expected);
    item.append(warn);
  }
  return item;
}

/** 上演中に新しい端末が来たら、上演の画面の上に知らせの帯（U5）。入り直し（合い札）の端末は承認済みで来るので出ない */
function renderBanner() {
  const box = $('joinBanner');
  const items = bannerFor(session.peers, screen);
  box.hidden = !items.length;
  box.replaceChildren(...items.map((p) => { const d = document.createElement('div'); d.className = 'item'; return requestItem(d, p); }));
}

// 承認した端末ごとの道を読み直す（つないだあとも ICE が道を替えることがある）
setInterval(async () => {
  let changed = false;
  for (const [id, conn] of conns) {
    const p = session.peers.get(id);
    if (!p || p.status !== 'approved') continue;
    const way = await routeState(conn);
    if (way && ways.get(id) !== way) { ways.set(id, way); changed = true; }
  }
  if (changed) { renderChips(); renderPeers(); }
}, 5000);

/** 受付の一覧に添える道（開演前の接続テストを兼ねる。聞き手が入ること自体がテスト） */
function wayLine(p) {
  const way = ways.get(p.id);
  return way ? ` · ${t(way === 'relay' ? 'routeRelay' : 'routeDirect')}` : '';
}

/** 聞き手ごとの札（U3）。各端末の報告（view）と、語り手が出させているもの（枚・動画を始めたか）を比べる */
function renderChips() {
  const box = $('chips');
  const approved = [...session.peers.values()].filter((p) => p.status === 'approved');
  if (!approved.length) { box.replaceChildren(Object.assign(document.createElement('div'), { className: 'muted', textContent: t('chipNone') })); return; }
  const expect = { slide: session.slide, video: !!session.playback.id };
  box.replaceChildren(...approved.map((p) => {
    const c = chipState(p.view, expect);
    const chip = document.createElement('div');
    chip.className = `chip ${c.level}`;
    chip.dataset.peer = p.id;
    chip.dataset.level = c.level;
    const part = (text, bad) => { const e = document.createElement('span'); e.textContent = text; if (bad) e.className = 'bad'; return e; };
    const parts = [part(who(p))];
    // 道（直接／中継）。語り手の画面だけに出す——聞き手（子供）には意味が無い
    const way = ways.get(p.id);
    if (way) parts.push(part(t(way === 'relay' ? 'routeRelay' : 'routeDirect')));
    const v = p.view;
    if (!v) parts.push(part(t('chipNoReport')));
    else {
      parts.push(part(t('chipSlide', v.slide), c.slide));
      const label = { picture: 'chipPicture', video: 'chipVideo', stream: 'chipStream', waiting: 'chipWaiting' }[v.show];
      parts.push(part(t(label) + (v.playing === false ? `（${t('chipPaused')}）` : ''), c.show));
      if (audios.length) parts.push(part(v.sound === 'on' ? t('soundOn') : v.sound === 'tap' ? t('soundTap') : t('chipSoundNone'), c.sound));
      if (c.receiving) parts.push(part(t('chipReceiving', fmtMB(v.recv.got), fmtMB(v.recv.all))));
    }
    // いまの枚のリンクの動画を、この端末では流せない（埋め込みを禁じられた・ネットに出られない）
    const linkBad = vCurrent && vCurrent.kind === 'link' ? linkProblems(p, vCurrent.id) : [];
    if (linkBad.length) { parts.push(part(t('chipLinkNo'), true)); chip.className = 'chip warn'; chip.dataset.level = 'warn'; }
    if (p.received < pictures.size) parts.push(part(t('pictures', p.received, pictures.size)));
    // 声（V10）: マイクの状態・届いているか・話しているかの印。届ける／届けないは語り手の側だけを変える（V5）
    const h = heardFrom(p, voice, voiceCtx());
    if (v) {
      const dot = document.createElement('span');
      dot.className = 'dot';
      dot.dataset.dot = p.id;
      const m = part(h.heard ? t('micHeard') : t('micWhy_' + (h.reason === 'mic' ? 'mic_' + v.mic : h.reason)), h.reason === 'same-room');
      m.prepend(dot);
      m.dataset.mic = h.heard ? 'heard' : h.reason;
      parts.push(m);
      if (h.reason === 'same-room') { chip.className = 'chip warn'; chip.dataset.level = 'warn'; }
    }
    for (const [i, e] of parts.entries()) { if (i) chip.append(' · '); chip.append(e); }
    if (v && v.mic === 'on') {
      const held = voice.held.has(p.id) || voice.sameRoom.has(p.id);
      const b = button(held ? t('voiceResume') : t('voiceHold'), () => {
        if (held) { voice.held.delete(p.id); voice.sameRoom.delete(p.id); } else voice.held.add(p.id);
        updateVoice();
      });
      b.className = 'mini';
      b.dataset.hold = p.id;
      chip.append(' ', b);
    }
    // 語り手と同じ部屋の端末では、語り手の声を鳴らさない（音の点呼で決める。ハウリング止め）。戻すのは語り手でも本人でもよい
    if (voice.quiet.has(p.id)) {
      chip.className = 'chip warn';
      chip.dataset.level = 'warn';
      chip.append(' · ', part(t('chipQuiet'), true));
      const b = button(t('quietResume'), () => { voice.quiet.delete(p.id); updateVoice(); });
      b.className = 'mini';
      b.dataset.quiet = p.id;
      chip.append(' ', b);
    }
    return chip;
  }));
}

// 名乗る前（端末どうしがまだつながっていない）の接続を、ICE の様子つきで出す
let tryingTimer = 0;
async function renderTrying() {
  clearTimeout(tryingTimer);
  const box = $('trying');
  if (!trying.size) { box.hidden = true; return; }
  const items = await Promise.all([...trying.values()].map(async (conn) => {
    const s = await iceState(conn);
    const device = String((conn.metadata && conn.metadata.device) || '').slice(0, 40);
    const item = li(`${t('tryingOne')} ${device} ${iceLine(s)}`.replace(/\s+/g, ' '), 'muted');
    // どこで止まっているか（ice.js の whyBlocked）。中継があるときは「同じ Wi-Fi」も Android の権限も聞かない
    const why = whyBlocked(s, { relay: relayOffered(), android: isAndroid(device) });
    if (why) {
      const p = document.createElement('div');
      p.className = 'warn';
      p.textContent = { 'local-net': t('blockedFrom', device), 'same-wifi': t('blockedOther'),
        'no-relay-here': t('blockedNoRelayHere'), 'no-relay-there': t('blockedNoRelayThere', device) }[why];
      item.append(p);
    }
    return item;
  }));
  box.hidden = false;
  box.replaceChildren(...items);
  tryingTimer = setTimeout(renderTrying, 2000);
}

function li(text, cls) { const e = document.createElement('li'); e.textContent = text; if (cls) e.className = cls; return e; }
function ul(lines) { const e = document.createElement('ul'); for (const l of lines) { const x = document.createElement('li'); x.textContent = l; e.append(x); } return e; }
function button(text, on) { const b = document.createElement('button'); b.textContent = text; b.addEventListener('click', on); return b; }

// ---------- 上演 ----------

function renderSlide() {
  const n = session.slide;
  const N = work.slides.length;
  const s = work.slides[n - 1];
  $('slideNo').textContent = t('slideOf', n, N);
  $('navNo').textContent = t('slideOf', n, N);
  $('slideTitle').textContent = s.title;
  setPicture($('current'), n);
  if (n < N) { setPicture($('next'), n + 1); $('nextLabel').textContent = t('nextPicture'); }
  else { $('next').removeAttribute('src'); $('nextLabel').textContent = t('end'); }
  $('next').hidden = !$('next').getAttribute('src'); // 最後の枚・絵の無い動画の枚: 空の枠（壊れた絵の印）を出さない
  // 直した枚は、直した後の文を出して印を付ける（E6。絵は作り直すまで古いまま＝決定 A）
  const applied = sheet ? applySheet(sheet, s) : null;
  const text = applied ? applied.notes : s.notes;
  const changed = new Set();
  if (applied && applied.edited.notes) {
    const was = new Set(paragraphs(s.notes));
    paragraphs(text).forEach((p, i) => { if (!was.has(p)) changed.add(i); });
  }
  // 台本: 行頭 "> " は語り手への合図として見た目を分ける。改行はそのまま（息継ぎの設計）
  // 行頭 "~ " は穴の語り（読む文。作る人・語る人が自分の話に替えてよい所）。印は出さず、字はそのまま蛍光ペンの形で出す
  const notes = $('notes');
  notes.replaceChildren();
  let para = 0, blank = true;
  for (const line of text.split('\n')) {
    const empty = !line.trim();
    if (!empty && blank && notes.childNodes.length) para++;
    blank = empty;
    const div = document.createElement('div');
    if (line.startsWith('> ')) { div.className = 'cue'; div.textContent = line.slice(2); }
    else if (line.startsWith('~ ')) { div.className = 'hole'; div.append(Object.assign(document.createElement('span'), { textContent: line.slice(2) })); }
    else div.textContent = line || ' ';
    if (!empty && changed.has(para)) div.classList.add('edited');
    notes.append(div);
  }
  notes.scrollTop = 0;
  renderOverlays(s, applied);
  $('editedMark').hidden = !(applied && (applied.edited.notes || applied.edited.boxes.size || applied.edited.layout.size));
  renderEditTools();
  $('prev').disabled = n <= 1;
  $('nextBtn').disabled = n >= N;
  renderVideoPanel();
  renderChips();
}

/** 画面の文字（E3）。語り手の画面にだけ文字で出す。直した枠は印、消す枠は取り消し線 */
function renderOverlays(s, applied) {
  const box = $('overlaysView');
  const list = s.overlays || [];
  box.hidden = !list.length || editing === s.number;
  if (box.hidden) { box.replaceChildren(); return; }
  const head = document.createElement('div');
  head.className = 'label';
  head.textContent = t('overlaysLabel');
  box.replaceChildren(head, ...list.map((b, i) => {
    const d = document.createElement('div');
    d.className = 'box';
    const now = applied ? applied.overlays[i] : b;
    if (applied && applied.edited.boxes.has(i + 1)) d.classList.add(now ? 'edited' : 'removed');
    d.textContent = boxText(now || b);
    return d;
  }));
}

// ---------- 直す欄（E1・E4・E6・決定4） ----------

const editCtx = () => ({ draft: !!(work && work.draft), roomOpen: !!peer });

/** 直す・修正票・読み直しの出し入れ（練習用の版で受付を開いていないときだけ。読み直しは受付を開いていないとき） */
function renderEditTools() {
  const n = session.slide;
  const can = !!work && editable(editCtx());
  $('editBtn').hidden = !can || editing === n;
  $('notes').hidden = editing === n;
  $('editPane').hidden = editing !== n;
  $('sheetBtn').hidden = !sheet;
  if (sheet) $('sheetBtn').textContent = t('sheetBtn', sheetCounts(sheet, statusOf, sigNow()));
  if (!sheet) $('sheetPanel').hidden = true;
  $('reloadLabel').hidden = !mayReload({ hasWork: !!work, roomOpen: !!peer });
  renderPicBar();
  renderVolBar();
}

// ---------- 絵の作り直しを頼む（M4） ----------
// 何をどう直したいかの文を修正票に入れる。作り直すのは作り手（生成した絵は候補を作って選ぶ・写真や子供の絵は差し替える）。
// 絵の位置の印はまだ作らない（2026-10-26 の決定: 文だけで取り違えが起きたら足す）

const pictureItem = (n) => (sheet ? sheet.items.find((x) => x.kind === 'picture' && x.slide === n) : null);
let picBarSlide = null; // 欄に入れた文がどの枚のものか（枚を動かしたら、その枚の頼みを入れ直す）

function renderPicBar() {
  const n = session.slide;
  const can = !!work && !!sheet && editable(editCtx()) && pictures.has(n);
  $('picBar').hidden = !can;
  if (!can) { picBarSlide = null; renderCandBar(n); return; }
  const x = pictureItem(n);
  if (picBarSlide !== n) { $('picComment').value = (x && x.comment) || ''; picBarSlide = n; }
  $('picSheet').textContent = !x ? t('picHint') : x.use ? t('picChosen', candName(x.use)) : t('picSheet', x.comment);
  const ask = $('picAsk');
  ask.textContent = t(x && x.comment ? 'picAskAgain' : 'picAsk');
  ask.disabled = !$('picComment').value.trim();
  ask.title = ask.disabled ? t('picNeedText') : '';
  renderCandBar(n);
}

$('picComment').addEventListener('input', () => {
  const ask = $('picAsk');
  ask.disabled = !$('picComment').value.trim();
  ask.title = ask.disabled ? t('picNeedText') : '';
});
$('picAsk').addEventListener('click', () => {
  const n = session.slide;
  const p = pictures.get(n);
  if (!p || !sheet || !editable(editCtx())) return;
  const next = askPicture(sheet, work.slides[n - 1], pictureIdent(p, work.slides[n - 1]), $('picComment').value);
  if (next === sheet) return; // 文が空（必須）
  sheet = next;
  saveSheet();
  renderSheet();
});

// ---------- 絵の候補を見くらべて選ぶ（§6 picture の Use） ----------
// 候補（pictures/_candidates/NN-K.png）は選ばれるまで絵を変えない。作り手がここで見くらべて選ぶと、修正票に Use が入る。
// 差し替え（gen_images.py --use）は作り手の PC の段。プレイヤーは作品を変えない（2026-10-29 選ばれない候補が残り、同じ頼みが2度来た）

let cand = null; // 開いている見くらべ: { n, list: [{ key, file, k }], i, url }
const candName = (key) => String(key).split('/').pop().replace(/\.[^.]+$/, '');
const candidatesNow = (n) => resolveCandidates(n, [workMap, mediaMap]);

function renderCandBar(n) {
  const list = !$('picBar').hidden ? candidatesNow(n) : [];
  $('candBar').hidden = !list.length;
  if (list.length) $('candNow').textContent = t('candNow', list.length);
  if (cand && (cand.n !== n || !list.length || !editable(editCtx()))) closeCand();
}

function openCand() {
  const n = session.slide;
  const list = candidatesNow(n);
  if (!list.length || !work) return;
  const x = pictureItem(n);
  const at = x && x.use ? list.findIndex((c) => c.key === x.use) : -1;
  cand = { n, list, i: Math.max(0, at), url: null };
  $('candTitle').textContent = t('candTitle', n);
  if (urls.get(n)) $('candCur').src = urls.get(n); else $('candCur').removeAttribute('src');
  $('candPanel').hidden = false;
  showCand();
  $('candUse').focus();
}

function closeCand() {
  if (!cand) return;
  if (cand.url) URL.revokeObjectURL(cand.url);
  cand = null;
  $('candPanel').hidden = true;
  $('candImg').removeAttribute('src');
  $('candBoxes').replaceChildren();
}

function showCand() {
  const c = cand.list[cand.i];
  if (cand.url) URL.revokeObjectURL(cand.url);
  cand.url = URL.createObjectURL(c.file);
  const img = $('candImg');
  img.classList.remove('fill');
  img.onload = () => { fitCand(); drawCandWords(); };
  img.src = cand.url;
  $('candCap').textContent = t('candOf', candName(c.key), cand.i + 1, cand.list.length);
  $('candPrev').disabled = cand.i === 0;
  $('candNext').disabled = cand.i === cand.list.length - 1;
  const x = pictureItem(cand.n);
  const chosen = !!(x && x.use === c.key);
  $('candUse').textContent = t(chosen ? 'candChosen' : 'candUse');
  $('candUse').disabled = chosen;
}

/** ビルダーと同じ合わせ方（§2.6）: 16:9 との差が 2% 以内なら引き伸ばし、ほかは黒地に全体 */
function fitCand() {
  const img = $('candImg');
  if (!img.naturalWidth || !img.naturalHeight) return;
  const r = (img.naturalWidth / img.naturalHeight) / (16 / 9);
  img.classList.toggle('fill', Math.abs(r - 1) <= 0.02);
}

/** 画面の文字のある枚は、候補の上にも文字を重ねる（上演したときの見え方で比べる。描き手は下書きと同じ boxElement） */
function drawCandWords() {
  const s = cand && work.slides[cand.n - 1];
  const stage = $('candStage');
  if (!s || !s.overlay_layout || !work.slide_size || !stage.clientWidth) { $('candBoxes').replaceChildren(); return; }
  const scale = stage.clientWidth / work.slide_size.width;
  const nodes = [];
  s.overlay_layout.forEach((box, i) => {
    const words = (s.overlays || [])[i];
    if (words && words.length) nodes.push(boxElement(document, box, words, scale));
  });
  $('candBoxes').replaceChildren(...nodes);
}

$('candOpen').addEventListener('click', openCand);
$('candClose').addEventListener('click', closeCand);
$('candPrev').addEventListener('click', () => { if (cand && cand.i > 0) { cand.i -= 1; showCand(); } });
$('candNext').addEventListener('click', () => { if (cand && cand.i < cand.list.length - 1) { cand.i += 1; showCand(); } });
$('candUse').addEventListener('click', () => {
  if (!cand || !sheet || !editable(editCtx())) return;
  const n = cand.n;
  const p = pictures.get(n);
  const next = choosePicture(sheet, work.slides[n - 1], pictureIdent(p, work.slides[n - 1]), cand.list[cand.i].key);
  if (next === sheet) return;
  sheet = next;
  saveSheet();
  picBarSlide = null; // 欄の文を、選んだ件に合わせて入れ直す
  renderSheet();
  showCand();
});
// どれもちがう: 見くらべを閉じて、これまでの「作り直したい」の欄へ
$('candNone').addEventListener('click', () => { closeCand(); $('picComment').focus(); });
$('candPanel').addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { e.preventDefault(); closeCand(); $('candOpen').focus(); }
  else if (e.key === 'ArrowLeft') { e.preventDefault(); $('candPrev').click(); }
  else if (e.key === 'ArrowRight') { e.preventDefault(); $('candNext').click(); }
});
window.addEventListener('resize', () => { if (cand) drawCandWords(); });

function openEditor() {
  const s = work.slides[session.slide - 1];
  const step = editorStep(editing, { type: 'open', slide: s.number }, editCtx());
  if (step.commit) commitEditor();
  editing = step.open;
  if (editing == null) return renderSlide();
  const applied = applySheet(sheet || emptySheet(work.title), s);
  $('editNotes').value = applied.notes;
  // 前回のひとこと（作品が変わったあと）は欄に入れない——入れたまま閉じると、今回の直しの理由として修正票に出る（2026-10-29 実際の作品で）
  editOld = !!sheet && isOldComment(sheet, s.number, sigNow());
  $('editComment').value = editOld ? '' : (sheet && sheet.comments[s.number]) || '';
  renderOldComment();
  editBoxes = (s.overlays || []).map((b, i) => ({ removed: applied.overlays[i] === null, fields: fieldsFromBox(applied.overlays[i] || b) }));
  editLayout = (s.overlay_layout || []).map((b, i) => applied.layout[i] || editOf(b, (s.overlays || [])[i]));
  laySel = -1;
  renderEditBoxes();
  renderSlide();
  renderLayout(); // 直す欄が出てから描く（隠れている間は幅0。閉じて開いても大きさが変わらなければ ResizeObserver は呼ばれない）
  $('editNotes').focus();
}

/** 画面の文字の直す欄: 枠ごとに、段落ごとの欄を並べる（欄の中の改行＝段落内改行。「段落を足す」＝新しい段落） */
function renderEditBoxes() {
  const host = $('editBoxes');
  if (!editBoxes.length) { host.replaceChildren(Object.assign(document.createElement('p'), { className: 'muted', textContent: t('noBoxes') })); return; }
  host.replaceChildren(...editBoxes.map((b, i) => {
    const d = document.createElement('div');
    d.className = 'ebox' + (b.removed ? ' removed' : '');
    const head = document.createElement('div');
    head.className = 'row';
    const name = document.createElement('strong');
    name.textContent = t('editBox', i + 1);
    head.append(name);
    if (b.removed) {
      const why = document.createElement('span');
      why.className = 'muted';
      why.textContent = t('boxRemoved');
      head.append(why, button(t('keepBox'), () => { b.removed = false; renderEditBoxes(); }));
      d.append(head);
      return d;
    }
    const add = button(t('addPara'), () => { b.fields.push({ text: '', orig: null }); renderEditBoxes(); });
    const del = button(t('removeBox'), () => { b.removed = true; renderEditBoxes(); });
    add.className = del.className = 'mini';
    head.append(add, del);
    d.append(head);
    for (const f of b.fields) {
      const ta = document.createElement('textarea');
      ta.rows = Math.max(1, f.text.split('\n').length);
      ta.value = f.text;
      ta.addEventListener('input', () => { f.text = ta.value; ta.rows = Math.max(1, ta.value.split('\n').length); renderLayout(); });
      d.append(ta);
    }
    return d;
  }));
  renderLayout(); // 直した文も、絵の上の下書きにそのまま描く（L4）
}

/** 直す欄の「前回のひとこと」の行（見て消す。新しく書けば置き換わる） */
let editOld = false;
function renderOldComment() {
  const row = $('editOldComment');
  const c = editOld && editing != null && sheet ? sheet.comments[editing] : '';
  row.hidden = !c;
  if (!c) return;
  $('editOldText').textContent = c;
}
$('editOldRemove').addEventListener('click', () => {
  if (editing == null || !sheet) return;
  sheet = removeComment(sheet, editing);
  editOld = false;
  saveSheet();
  renderSheet();
  renderOldComment();
});

/** 開いている直す欄を修正票に入れる（work.json は変えない） */
function commitEditor() {
  if (editing == null || !work || !sheetEnabled(work)) return;
  const s = work.slides[editing - 1];
  if (!s) return;
  sheet = setSlideEdits(sheet || emptySheet(work.title), s, {
    notes: $('editNotes').value,
    overlays: editBoxes.map((b) => (b.removed ? [] : boxFromFields(b.fields))),
    layout: s.overlay_layout ? editLayout : undefined,
    // 前回のひとことが残っていて欄が空＝触れていない（undefined）。書けば置き換わる
    comment: editOld && !$('editComment').value.trim() ? undefined : $('editComment').value,
  }, sigNow());
  saveSheet();
  renderSheet();
}

/** ev: close（修正票に入れる）| cancel | move | room（受付を開いた: 書きかけは修正票の下書きとして残す） */
function closeEditor(ev) {
  const step = editorStep(editing, ev, editCtx());
  if (step.commit) commitEditor();
  editing = step.open;
  editBoxes = [];
  editLayout = [];
  laySel = -1;
  renderLayout();
  if (work) renderSlide();
}

$('editBtn').addEventListener('click', openEditor);
$('editDone').addEventListener('click', () => closeEditor({ type: 'close' }));
$('editCancel').addEventListener('click', () => closeEditor({ type: 'cancel' }));

// ---------- 絵の上で直す（overlay_layout。L1〜L4） ----------
// 文字の枠だけ抜いた下敷き（PowerPoint が描いた絵）の上に、ブラウザが枠を描く。
// ⚠️ これは直すための下書き。正しい絵は作り直した PPTX で、聞き手・練習・上演の画面は焼き込まれた絵のまま（L8）

const SNAP_PX = 6;                 // 中央の線への吸い付きの許容（画面の px）
let layDrag = null;                // ドラッグ中: { i, corner, start, sx, sy }

/** 絵の上で直す枚（直す欄を開いていて、置き場所があり、下敷きが見つかったときだけ。無ければ null） */
function layoutSlide() {
  if (editing == null || !work || !work.slide_size) return null;
  const s = work.slides[editing - 1];
  return s && s.overlay_layout && baseUrls.has(s.number) && editLayout.length === s.overlay_layout.length ? s : null;
}

const layScale = () => $('layStage').clientWidth / work.slide_size.width;

/** その枠を作品の元の値から変えたか（修正票に書く刻みで比べる。位置・大きさ・文字の大きさ・色——修正票の件と同じ物差し） */
function layChanged(s, i) {
  const a = sheetValues(editLayout[i]), b = sheetValues(editOf(s.overlay_layout[i], (s.overlays || [])[i]));
  return LAYOUT_KEYS.some((k) => a[k] !== undefined && a[k] !== b[k]);
}

/** 下敷きの上に枠を描き直す。文字は「直す」欄の中身（L4）。消す枠・全部空にした枠は描かない */
function renderLayout() {
  const s = layoutSlide();
  $('layPane').hidden = !s;
  if (!s) { $('layBoxes').replaceChildren(); $('laySel').hidden = true; $('layFields').hidden = true; return; }
  const stage = $('layStage');
  stage.style.aspectRatio = `${work.slide_size.width} / ${work.slide_size.height}`;
  const base = baseUrls.get(s.number);
  if ($('layBase').getAttribute('src') !== base) $('layBase').src = base;
  const pic = urls.get(s.number);
  $('layPic').hidden = !($('layOver').checked && pic);
  if (pic && $('layPic').getAttribute('src') !== pic) $('layPic').src = pic;
  const scale = layScale();
  if (!scale) return; // まだ画面に出ていない（出たら ResizeObserver が描き直す）
  const px = (emu) => `${emu * scale}px`;
  const nodes = [];
  s.overlay_layout.forEach((orig, i) => {
    const eb = editBoxes[i];
    if (!eb || eb.removed) return;
    const words = boxFromFields(eb.fields);
    if (!words.length) return;
    const el = boxElement(document, applyEdit(orig, editLayout[i]), words, scale);
    if (layChanged(s, i)) el.classList.add('edited');
    el.dataset.i = String(i);
    nodes.push(el);
  });
  $('layBoxes').replaceChildren(...nodes);
  const shown = laySel >= 0 && nodes.some((n) => n.dataset.i === String(laySel));
  $('laySel').hidden = !shown;
  if (shown) {
    const e = editLayout[laySel];
    Object.assign($('laySel').style, { left: px(e.x), top: px(e.y), width: px(e.width), height: px(e.height) });
  }
  renderLayFields(shown);
}

/** 選んだ枠の数値（インチ・ポイント）。打っている最中の欄は書き換えない */
function renderLayFields(shown) {
  $('layFields').hidden = !shown;
  $('layColors').hidden = !shown;
  if (!shown) return;
  const e = editLayout[laySel];
  $('layName').textContent = t('editBox', laySel + 1);
  const set = (id, v) => { if (document.activeElement !== $(id)) $(id).value = v; };
  set('layLeft', toIn(e.x).toFixed(2));
  set('layTop', toIn(e.y).toFixed(2));
  set('layWidth', toIn(e.width).toFixed(2));
  set('layHeight', toIn(e.height).toFixed(2));
  set('laySize', String(Math.round(e.size)));
  renderLayColors(e);
}

// ---------- 文字色と下地の色（§6 の color・fill）・明暗差の目安（§3.2） ----------

let layPalette = { work: null, colors: [] };      // 色見本（作品ごとに1回だけ数える）
const layPixels = new Map();                      // 下敷きの URL → { w, h, g }（明暗差を測る画素。下敷きごとに1回だけ描く）

const paletteNow = () => {
  if (layPalette.work !== work) layPalette = { work, colors: workPalette(work) };
  return layPalette.colors;
};

/** 色見本のボタンを並べ、いまの色に印を付ける。onPick(色) */
function swatches(el, cur, onPick) {
  const colors = paletteNow();
  if (el.dataset.colors !== colors.join(',')) {
    el.replaceChildren(...colors.map((c) => {
      const b = document.createElement('button');
      Object.assign(b, { type: 'button', title: c });
      b.dataset.c = c;
      b.style.background = c;
      b.setAttribute('aria-label', c);
      b.addEventListener('click', () => onPick(c));
      return b;
    }));
    el.dataset.colors = colors.join(',');
  }
  for (const b of el.children) b.classList.toggle('on', b.dataset.c === cur);
}

/** 下敷きの、枠の中の明るさの平均（測れなければ NaN）。§3.2: 枠の矩形・回転は無視 */
function baseLuma(e) {
  const img = $('layBase');
  const url = img.getAttribute('src');
  if (!url || !img.complete || !img.naturalWidth) return NaN;
  let px = layPixels.get(url);
  if (!px) {
    try {
      const c = document.createElement('canvas');
      c.width = img.naturalWidth; c.height = img.naturalHeight;
      const g = c.getContext('2d', { willReadFrequently: true });
      g.drawImage(img, 0, 0);
      px = { w: c.width, h: c.height, g };
      layPixels.set(url, px);
    } catch { return NaN; }
  }
  const sx = px.w / work.slide_size.width, sy = px.h / work.slide_size.height;
  const x0 = Math.max(0, Math.floor(e.x * sx)), y0 = Math.max(0, Math.floor(e.y * sy));
  const x1 = Math.min(px.w, Math.floor((e.x + e.width) * sx)), y1 = Math.min(px.h, Math.floor((e.y + e.height) * sy));
  if (x1 <= x0 || y1 <= y0) return NaN;
  try { return meanLuma(px.g.getImageData(x0, y0, x1 - x0, y1 - y0).data); } catch { return NaN; }
}

/** 選んだ枠の色の欄。段落で色が割れた枠は文字の色を直せない（ひとことで頼む）。明暗差は印だけで、選ぶのは止めない */
function renderLayColors(e) {
  const mixed = !e.color;
  $('layColorMixed').hidden = !mixed;
  $('layColorSw').hidden = mixed;
  $('layColorPick').hidden = mixed;
  if (!mixed) {
    swatches($('layColorSw'), e.color, (c) => laySel >= 0 && setLay({ ...editLayout[laySel], color: c }));
    if (document.activeElement !== $('layColorPick')) $('layColorPick').value = e.color.toLowerCase();
  }
  swatches($('layFillSw'), e.fill, (c) => laySel >= 0 && setLay({ ...editLayout[laySel], fill: c }));
  if (document.activeElement !== $('layFillPick')) $('layFillPick').value = (e.fill || '#FFFFFF').toLowerCase();
  $('layFillNone').classList.toggle('on', !e.fill);
  const c = contrast(e, e.fill ? NaN : baseLuma(e));
  $('layContrast').hidden = !c;
  if (c) {
    $('layContrast').textContent = t('layContrast', Math.round(c.gap), c.low);
    $('layContrast').title = t('layContrastHint');
    $('layContrast').classList.toggle('low', c.low);
  }
}

$('layColorPick').addEventListener('input', () => {
  if (laySel >= 0 && editLayout[laySel].color) setLay({ ...editLayout[laySel], color: $('layColorPick').value.toUpperCase() });
});
$('layFillPick').addEventListener('input', () => {
  if (laySel >= 0) setLay({ ...editLayout[laySel], fill: $('layFillPick').value.toUpperCase() });
});
$('layFillNone').addEventListener('click', () => laySel >= 0 && setLay({ ...editLayout[laySel], fill: null }));
$('layBase').addEventListener('load', () => { if (layoutSlide()) renderLayout(); });   // 明暗差は下敷きを読み終えてから測れる

function showGuides(g) {
  $('layGuideV').hidden = !(g && g.v);
  $('layGuideH').hidden = !(g && g.h);
}

function setLay(e) {
  if (laySel < 0) return;
  editLayout[laySel] = e;
  renderLayout();
}

$('layStage').addEventListener('pointerdown', (ev) => {
  if (!layoutSlide() || ev.button !== 0) return;
  const corner = ev.target.dataset && ev.target.dataset.corner;
  const hit = ev.target.closest && ev.target.closest('.b');
  if (corner && laySel >= 0) layDrag = { i: laySel, corner };
  else if (hit) { laySel = Number(hit.dataset.i); layDrag = { i: laySel, corner: null }; }
  else { laySel = -1; layDrag = null; renderLayout(); $('layStage').focus(); return; }
  Object.assign(layDrag, { start: editLayout[layDrag.i], sx: ev.clientX, sy: ev.clientY });
  $('layStage').setPointerCapture(ev.pointerId);
  ev.preventDefault();
  $('layStage').focus();
  renderLayout();
});

$('layStage').addEventListener('pointermove', (ev) => {
  if (!layDrag) return;
  const k = 1 / layScale();
  const dx = (ev.clientX - layDrag.sx) * k, dy = (ev.clientY - layDrag.sy) * k;
  if (layDrag.corner) {
    editLayout[layDrag.i] = resizeBy(layDrag.start, layDrag.corner, dx, dy);
  } else {
    const r = moveBy(layDrag.start, dx, dy, work.slide_size, SNAP_PX * k);
    editLayout[layDrag.i] = r.edit;
    showGuides(r.guides);
  }
  renderLayout();
});

const endDrag = () => { layDrag = null; showGuides(null); };
$('layStage').addEventListener('pointerup', endDrag);
$('layStage').addEventListener('pointercancel', endDrag);

// 矢印キー（0.01インチ・Shift で 0.1インチ）。⚠️ 枚送りのキーはここでは効かない（document の keydown が .lay を除く）
$('layStage').addEventListener('keydown', (ev) => {
  if (laySel < 0) return;
  if (ev.key.startsWith('Arrow')) { ev.preventDefault(); setLay(nudge(editLayout[laySel], ev.key, ev.shiftKey)); }
  else if (ev.key === 'Escape') { laySel = -1; renderLayout(); }
});

for (const [id, k] of [['layLeft', 'x'], ['layTop', 'y'], ['layWidth', 'width'], ['layHeight', 'height']]) {
  $(id).addEventListener('input', () => {
    const v = parseFloat($(id).value);
    if (laySel < 0 || !Number.isFinite(v) || ((k === 'width' || k === 'height') && v < 0.1)) return;
    setLay({ ...editLayout[laySel], [k]: fromIn(v) });
  });
  $(id).addEventListener('blur', () => renderLayout()); // 打ち終えたら、修正票に書く刻みの値で出し直す
}
$('laySize').addEventListener('input', () => {
  const v = parseFloat($('laySize').value);
  if (laySel >= 0 && Number.isFinite(v) && v >= 1) setLay({ ...editLayout[laySel], size: Math.round(v) });
});
$('laySize').addEventListener('blur', () => renderLayout());
$('laySmaller').addEventListener('click', () => laySel >= 0 && setLay(resize(editLayout[laySel], -1)));
$('layBigger').addEventListener('click', () => laySel >= 0 && setLay(resize(editLayout[laySel], 1)));
// 元に戻す: その枠を作品の元の値（書き出したときの値）へ
$('layReset').addEventListener('click', () => {
  const s = layoutSlide();
  if (s && laySel >= 0) setLay(editOf(s.overlay_layout[laySel], (s.overlays || [])[laySel]));
});
$('layOver').addEventListener('change', () => renderLayout());
// 変数に持っておく（どこからも指していない observer を残さない）
const layObserver = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(() => { if (layoutSlide()) renderLayout(); }) : null;
if (layObserver) layObserver.observe($('layStage'));

// ---------- 修正票（E5・F2） ----------

/** ブラウザの中の修正票を読む。⚠️ 練習用の版のときだけ（家族向けの版を同じブラウザで開いても出さない） */
function loadSheet(w) {
  if (!sheetEnabled(w)) return null;
  let raw = null;
  try { raw = localStorage.getItem(storageKey(w.title)); } catch { /* 保存できないブラウザ（このページのあいだだけ持つ） */ }
  return readSheet(raw, w.title);
}

function saveSheet() {
  if (!sheet) return;
  try {
    if (isEmpty(sheet)) localStorage.removeItem(storageKey(sheet.title));
    else localStorage.setItem(storageKey(sheet.title), JSON.stringify(sheet));
  } catch { /* 同上 */ }
}

function forgetSheet(title) {
  try { localStorage.removeItem(storageKey(title)); } catch { /* 同上 */ }
}

/** いまの作品のしるし（ひとことの判定。作品が替わったときだけ計算し直す） */
let sigMemo = { work: null, sig: null };
function sigNow() {
  if (!work) return null;
  if (sigMemo.work !== work) sigMemo = { work, sig: workSig(work) };
  return sigMemo.sig;
}

/** 絵の件で見る絵のファイルの見分け（大きさ・更新日時）。組み立ての元の絵（picture_source）があればそのファイル——
 *  文字を載せた絵（_built）は組み立てるたびに書き直されるので見分けに使わない（Issue #5）。元の絵が手元に無ければ null（パスだけで見る） */
function pictureIdent(p, slideData) {
  if (!p || !slideData) return null;
  const f = slideData.picture_source ? (p.source && p.source.file) : p.file;
  return f ? { size: f.size, modified: f.lastModified } : null;
}

/** 指した絵・コマ・区間の動画の、いまのファイルの見分け（大きさ・更新日時。§6）。list＝動画の一覧（n・k・file）・pics＝枚の番号 → 絵 */
function identOf(list, x, pics) {
  if (x.kind === 'picture') {
    const p = pics.get(x.slide);
    const id = p && work ? pictureIdent(p, work.slides[x.slide - 1]) : null;
    if (!id) return null;
    // 候補から選んだ件: 選んだ候補がまだあるか（--use で差し替えると _candidates から無くなる＝反映済み）
    const left = x.use ? { useLeft: [workMap, mediaMap].some((m) => m.has(x.use)) } : {};
    return { ...id, ...left };
  }
  const v = list.find((y) => y.n === x.slide && y.k === videoOf(x));
  return v ? { size: v.file.size, modified: v.file.lastModified } : null;
}
const statusOf = (x) => (work.slides[x.slide - 1]
  ? judge(x, work.slides[x.slide - 1], (y) => identOf(videos, y, pictures))
  : isMedia(x) ? 'changed' : 'reworded');
/** Markdown に書かない件（手を入れて反映した件・指したコマや動画が変わった件。Claude にもう一度当てさせない） */
const skipped = () => new Set(sheet.items.map((x, i) => (['reworded', 'changed'].includes(statusOf(x)) ? i : -1)).filter((i) => i >= 0));

function renderSheet() {
  renderEditTools();
  const list = $('sheetList');
  if (!sheet) { list.replaceChildren(); return; }
  // ボタンの数と同じ見出しで分ける（未反映／見て消す／反映済み）。札は「なぜそこにいるか」だけ・ボタンは見出しごとに意味を変える（2026-10-27）
  const g = sheetGroups(sheet, statusOf, sigNow());
  const shownComment = new Set();
  const badgeOf = (st, comment) => (st === 'pending' ? null
    : t(comment ? 'stCommentChanged' : st === 'reworded' ? 'stReworded' : st === 'changed' ? 'stChanged' : 'stDone'));
  const head = (text, st, comment, act) => {
    const d = document.createElement('div');
    d.className = 'item-head';
    d.textContent = text;
    const b = badgeOf(st, comment);
    if (b) d.append(' — ', Object.assign(document.createElement('span'), { className: `st-${st}`, textContent: b }));
    d.append(' ', button(t(st === 'pending' ? 'withdrawItem' : 'checkedItem'), act));
    return d;
  };
  const itemRow = (r) => {
    const x = sheet.items[r.i];
    const item = li('');
    item.append(head(`[${x.slide}] ${place(x)}`, r.st, false, () => { sheet = removeItem(sheet, r.i); saveSheet(); renderSheet(); renderSlide(); }));
    const show = (side) => (x.kind === 'layout' ? textOf(x, side).replace(/\n/g, '  ') : textOf(x, side));
    const pre = document.createElement('pre');
    pre.textContent = isMedia(x) ? mediaLines(x).join('\n') : `${show('before') || '—'}\n→ ${show('after') || '（—）'}`;
    item.append(pre);
    // 文の件のある枚のひとことは、その枚の最初の件に添える（ここに出さないと、どこにも見えない）
    const c = isOldComment(sheet, x.slide, sigNow()) ? null : sheet.comments[x.slide]; // 前回のひとことは「見て消す」の行に出す
    if (c && !shownComment.has(x.slide)) {
      shownComment.add(x.slide);
      item.append(Object.assign(document.createElement('pre'), { className: 'sheet-comment', textContent: t('sheetCommentOf', c) }));
    }
    return item;
  };
  const commentRow = (r) => {
    const item = li('');
    item.append(head(`[${r.slide}] ${t('stComment')}`, r.st, true, () => { sheet = removeComment(sheet, r.slide); saveSheet(); renderSheet(); }),
      Object.assign(document.createElement('pre'), { textContent: sheet.comments[r.slide] }));
    return item;
  };
  const rows = [];
  for (const [key, arr] of [['sheetGroupPending', g.pending], ['sheetGroupLook', g.look], ['sheetGroupDone', g.done]]) {
    if (!arr.length) continue;
    rows.push(li(t(key, arr.length), 'sheet-group'));
    for (const r of arr) rows.push(r.kind === 'item' ? itemRow(r) : commentRow(r));
  }
  if (!rows.length) rows.push(li(t('sheetEmpty'), 'muted'));
  list.replaceChildren(...rows);
}

$('sheetBtn').addEventListener('click', () => {
  const open = $('sheetPanel').hidden;
  $('sheetPanel').hidden = !open;
  $('sheetBtn').setAttribute('aria-expanded', String(open));
  if (open) { commitEditor(); renderSheet(); }
});

$('sheetCopy').addEventListener('click', async () => {
  if (!sheet) return;
  commitEditor();
  try {
    await navigator.clipboard.writeText(sheetMarkdown(sheet, new Date(), skipped(), sigNow()));
    $('sheetNote').textContent = t('sheetCopied');
  } catch (err) {
    $('sheetNote').textContent = t('sheetSaveFailed', String((err && err.message) || err));
  }
});

$('sheetSave').addEventListener('click', async () => {
  if (!sheet) return;
  commitEditor();
  const text = sheetMarkdown(sheet, new Date(), skipped(), sigNow());
  const name = sheetName(work.title, new Date());
  try {
    if (typeof window.showSaveFilePicker === 'function') {
      // 作品フォルダで開く（直下に置くと、書き戻す人が作品の隣で見つけられる）。録画は大きいので作品フォルダへ寄せない
      const h = await window.showSaveFilePicker({ suggestedName: name, ...(workDir ? { startIn: workDir } : {}),
        types: [{ description: 'Markdown', accept: { 'text/markdown': ['.md'] } }] });
      const w = await h.createWritable();
      await w.write(text);
      await w.close();
    } else {
      const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(new Blob([text], { type: 'text/markdown' })), download: name });
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    }
    $('sheetNote').textContent = t('sheetSaved');
  } catch (err) {
    if (!(err && err.name === 'AbortError')) $('sheetNote').textContent = t('sheetSaveFailed', String((err && err.message) || err));
  }
});

function setPicture(img, n) {
  const u = urls.get(n);
  if (u) img.src = u; else img.removeAttribute('src');
}

function move(delta) {
  if (!work) return;
  const before = session.slide;
  const out = goTo(session, session.slide + delta, work.slides.length);
  if (session.slide === before) return;
  if (editing != null) closeEditor({ type: 'move' }); // 枚を動かしたら、開いている直す欄は修正票に入れて閉じる
  if (session.playback.id) stopVideo(); // 枚を離れたら動画を止め、聞き手の画面を絵へ戻す
  chosenVideo = null;                    // 新しい枚では1本目から
  send(out);
  send(slideAudio(session, work, idOf, Date.now()));
  playHere(true);
  clock = clockSlide(clock, Date.now());
  renderSlide();
  renderClock();
  updateVoice(); // BGM が始まった・止まった（V7）
}

$('prev').addEventListener('click', () => move(-1));

// ---------- 左右の境目（U8）。左＝聞き手の画面、右＝台本。割合はこの端末のブラウザに覚える（覚えられなくても既定で動く） ----------

const SPLIT_KEY = 'dk-split';
function setSplit(v, save) {
  const pct = clampSplit(v);
  $('showGrid').style.setProperty('--split', `${pct}%`);
  const sp = $('splitter');
  sp.setAttribute('aria-valuenow', String(pct));
  sp.setAttribute('aria-valuemin', String(SPLIT_MIN));
  sp.setAttribute('aria-valuemax', String(SPLIT_MAX));
  if (save) {
    try { if (pct === SPLIT_DEFAULT) localStorage.removeItem(SPLIT_KEY); else localStorage.setItem(SPLIT_KEY, String(pct)); } catch { /* 覚えられないブラウザ */ }
  }
  return pct;
}
let splitNow = (() => { try { return setSplit(localStorage.getItem(SPLIT_KEY), false); } catch { return setSplit(null, false); } })();
let splitDrag = false;
$('splitter').addEventListener('pointerdown', (e) => {
  if (e.button !== 0) return;
  splitDrag = true;
  $('splitter').classList.add('drag');
  $('splitter').setPointerCapture(e.pointerId);
  e.preventDefault();
});
$('splitter').addEventListener('pointermove', (e) => {
  if (!splitDrag) return;
  const r = $('showGrid').getBoundingClientRect();
  splitNow = setSplit(splitAt(e.clientX, r.left, r.width), false);
});
const endSplit = () => {
  if (!splitDrag) return;
  splitDrag = false;
  $('splitter').classList.remove('drag');
  setSplit(splitNow, true);
};
$('splitter').addEventListener('pointerup', endSplit);
$('splitter').addEventListener('pointercancel', endSplit);
$('splitter').addEventListener('dblclick', () => { splitNow = setSplit(SPLIT_DEFAULT, true); });
$('splitter').addEventListener('keydown', (e) => {
  const d = { ArrowLeft: -SPLIT_STEP, ArrowRight: SPLIT_STEP }[e.key];
  if (d) { e.preventDefault(); splitNow = setSplit(splitNow + d, true); }
  else if (e.key === 'Home') { e.preventDefault(); splitNow = setSplit(SPLIT_DEFAULT, true); }
});
$('nextBtn').addEventListener('click', () => move(1));
document.addEventListener('keydown', (e) => {
  // 枚送りのキーは上演の画面でだけ効く（受付の画面で押して、知らないうちに枚が進まないように）
  if (screen !== 'show' || cand || (e.target.matches && e.target.matches('input, textarea, video, .lay, .splitter'))) return;
  if (['ArrowRight', 'PageDown', ' '].includes(e.key)) { e.preventDefault(); move(1); }
  if (['ArrowLeft', 'PageUp'].includes(e.key)) { e.preventDefault(); move(-1); }
});

// ---------- 動画の再生（設計 #6・#7・#10） ----------
// 語り手は自分の画面の動画を、ふつうの操作つまみで再生・一時停止・頭出しする。その操作を合図にして配る。

const vEl = $('nvideo');
let vUrl = null;
let vCurrent = null;          // いまの枚の動画
let captured = null;          // 予備の「その場で流す」用の映像（captureStream）
let chosenVideo = null;       // 1枚に動画が複数あるとき、語り手が選んだ1本の id（W2。null＝1本目）
let tick = 0;
// リンクの動画（YouTube の埋め込み）の再生口。<video> と同じ形なので、合図は同じ道で配る
const linkP = new LinkPlayer($('nlink'));
/** いまの動画の再生口（ファイルなら <video>、リンクなら埋め込み） */
const cur = () => (vCurrent && vCurrent.kind === 'link' ? linkP : vEl);
/** 枠に出す動画の一覧（ファイルとリンクを、書いた順に） */
const panelVideos = () => [...videos, ...links].sort((a, b) => a.n - b.n || a.k - b.k);

/** 聞き手の画面の枠（U2）。動画の枚では、枠そのものが動画の再生つまみになる。
 *  再生を始めるまでは、聞き手の端末と同じく絵を出しておく（poster） */
function renderVideoPanel() {
  const list = videosOn(panelVideos(), session.slide);
  const v = pickVideo(list, chosenVideo);
  renderVideoPick(list, v);
  const isLink = !!v && v.kind === 'link';
  vEl.hidden = !v || isLink;
  $('nlink').hidden = !isLink;
  $('current').hidden = !!v;
  // 絵の無い枚は、動画の最初のコマ（聞き手の端末も、動画を受け取っていれば最初のコマを出す。work-format §2.4・2026-10-25 D4）
  if (v && urls.has(session.slide)) vEl.poster = urls.get(session.slide);
  else if (v) vEl.removeAttribute('poster');
  if (v === vCurrent) { renderMediaBars(); return; }
  vCurrent = v;
  closeBoard();
  captured = null;
  if (vUrl) { URL.revokeObjectURL(vUrl); vUrl = null; }
  $('videoNote').textContent = v && v.problem ? t('videoAllStream', t('why_' + v.problem)) : '';
  if (!isLink) linkP.unload();
  if (!v || isLink) { vEl.removeAttribute('src'); vEl.load(); }
  if (isLink) { linkP.load(v); renderLinkNote(); }
  if (!v || isLink) { renderMediaBars(); return; }
  vUrl = URL.createObjectURL(v.file);
  vEl.src = vUrl;
  renderMediaBars();
}

/** 1枚に動画が複数あるとき、枠の下に「動画 1／2／3」の切り替え（W2）。1本だけの枚では出さない */
function renderVideoPick(list, cur) {
  const box = $('videoPick');
  box.hidden = list.length < 2;
  if (box.hidden) { box.replaceChildren(); return; }
  box.replaceChildren(...list.map((x, i) => {
    const b = button(t('videoPick', i + 1, x.kind === 'link' ? t('linkName', fmtCut(x)) : videoName(x.key)), () => chooseVideo(x.id));
    b.dataset.video = x.id;
    b.title = x.key;
    if (cur && x.id === cur.id) { b.setAttribute('aria-pressed', 'true'); b.className = 'on'; }
    return b;
  }));
}

/** 別の1本を選んだ。流している途中なら止めて聞き手の画面を絵へ戻し、選んだ1本を枠に出す（再生は語り手が押す） */
function chooseVideo(id) {
  const next = pickVideo(videosOn(panelVideos(), session.slide), id);
  if (mustStopFor(next, session.playback.id)) stopVideo();
  chosenVideo = next ? next.id : null;
  renderVideoPanel();
  renderChips();
}

function control(action) {
  // 再生を始める前の頭出し・止めたあとに遅れて届く pause は合図にしない
  if (!vCurrent || (action !== 'play' && !session.playback.id)) return;
  send(playVideo(session, action, { id: vCurrent.id, pos: cur().currentTime, now: Date.now() }));
  if (session.playback.playing) {
    // 動画を流し始めたら BGM を止める・動画のあとも鳴らし直さない（2026-10-26 練習の修正票）
    // ⚠️ 聞き手がいなくても（練習）この端末の BGM は止める——合図の数（承認済みの聞き手の数）で決めない
    const before = session.audio;
    send(videoAudio(session, work, Date.now()));
    if (session.audio !== before) playHere(false);
  }
  engine.duck(session.playback.playing);
  updateVoice(); // 動画のあいだは聞き手の声を届けない（V6）
  renderChips();
  clearInterval(tick);
  if (session.playback.playing) {
    tick = setInterval(() => send(playVideo(session, 'seek', { pos: cur().currentTime, now: Date.now() })), TICK_MS);
    for (const id of conns.keys()) streamTo(id);
  }
}

// ⚠️ 2つの再生口のできごとは、いまの動画の口のものだけ受ける（切り替えた直後に、前の口の pause が遅れて届く）
const mine = (el, fn) => () => { if (cur() === el) fn(); };
vEl.addEventListener('play', mine(vEl, () => control('play')));
vEl.addEventListener('playing', () => { if (recorder) recorder.setVideo(vEl); }); // 録画に動画の音をつなぐ（動画ごとに流れが変わる）
vEl.addEventListener('pause', mine(vEl, () => control('pause')));
// 動画が最後まで流れたら、その枚の [BGM after video] を鳴らす（2026-10-29 実際の作品の修正票。途中で止めたときは鳴らさない）
function onEnded() {
  if (!work || !vCurrent || vCurrent.n !== session.slide) return;
  const before = session.audio;
  send(videoEndAudio(session, work, idOf, Date.now()));
  if (session.audio !== before) playHere(false);
}
vEl.addEventListener('ended', mine(vEl, onEnded));
vEl.addEventListener('seeked', mine(vEl, () => control(vEl.paused ? 'pause' : 'seek')));
// リンクの動画も同じ合図にする。止める秒で止まったら 'ended'（[BGM after video] もファイルの動画と同じに鳴る）
linkP.addEventListener('play', mine(linkP, () => control('play')));
linkP.addEventListener('pause', mine(linkP, () => control('pause')));
linkP.addEventListener('ended', mine(linkP, onEnded));
linkP.addEventListener('seeked', mine(linkP, () => control(linkP.paused ? 'pause' : 'seek')));
linkP.addEventListener('error', renderLinkNote);
linkP.addEventListener('ready', renderLinkNote);
linkP.addEventListener('stall', renderLinkNote);
linkP.addEventListener('play', renderLinkNote); // 始まらなかったのが、押し直して始まった

/** 流す範囲の短い表示（5:51–6:09） */
function fmtCut(x) {
  const m = (v) => `${Math.floor(v / 60)}:${String(Math.floor(v % 60)).padStart(2, '0')}`;
  return x.end != null ? `${m(x.start)}–${m(x.end)}` : `${m(x.start)}–`;
}

/** リンクの動画の枠の下: この端末で流せない・流せない聞き手がいる。例外の窓は出さず、ここに書く */
function renderLinkNote() {
  if (!vCurrent || vCurrent.kind !== 'link') return;
  const lines = [];
  if (linkP.error) lines.push(t('linkHereNo', t('linkWhy_' + linkP.error)));
  else if (linkP.stalled) lines.push(t('linkStall'));
  const bad = [...session.peers.values()].filter((p) => p.status === 'approved')
    .map((p) => [p, linkProblems(p, vCurrent.id)]).filter(([, w]) => w.length);
  if (bad.length) lines.push(t('linkPeersNo', bad.map(([p, w]) => `${who(p)}（${w.map((x) => t('linkWhy_' + x)).join('、')}）`).join('・')));
  const note = $('videoNote');
  note.textContent = lines.join(' ');
  note.classList.toggle('bad', lines.length > 0);
}

// ---------- エンディング動画のコマを指す（M1）・絵コンテ（M2） ----------
// 止めた位置のコマを「差し替えたい」と修正票に入れる。新しい写真を選ぶのは作り手（絵コンテのページで）。
// ⚠️ 席・写真の名前・カードの絵は語り手の画面だけ。聞き手へは送らない（R1。席は videos の一覧にも入れていない）

/** いまの動画がエンディング動画で席を持つなら、その席 */
function seatsOf(v) {
  const cue = v && work && work.slides[v.n - 1] ? videoCueOf(work.slides[v.n - 1], v.k) : null;
  return cue && cue.role === 'ending' && Array.isArray(cue.seats) && cue.seats.length ? cue.seats : null;
}
const pointedSeat = (v, n) => !!sheet && sheet.items.some((x) => x.kind === 'seat' && x.slide === v.n && x.video === v.k && x.at === n);

function renderSeatBar() {
  const seats = seatsOf(vCurrent);
  const can = !!seats && !!sheet && editable(editCtx());
  $('seatBar').hidden = !can;
  if (!can) { closeBoard(); return; }
  const at = vEl.currentTime || 0;
  const seat = seatAt(seats, at);
  $('seatNow').textContent = seat
    ? [t('seatNow', seat.n, seats.length, seatClock(at)), seat.label, seat.pin ? t('seatPinned', seat.pin) : ''].filter(Boolean).join(' · ')
    : t('seatNone', seatClock(at));
  const point = $('seatPoint');
  point.disabled = !seat || !vEl.paused;
  point.textContent = t(seat && pointedSeat(vCurrent, seat.n) ? 'seatPointAgain' : 'seatPoint');
  point.title = seat && !vEl.paused ? t('seatPaused') : '';
  $('seatComment').placeholder = t(seat && seat.pin ? 'seatPinnedPh' : 'seatCommentPh');
  markBoard(seat);
}

$('seatPoint').addEventListener('click', () => {
  const seats = seatsOf(vCurrent);
  if (!seats || !sheet || !editable(editCtx())) return;
  sheet = pointSeat(sheet, work.slides[vCurrent.n - 1], vCurrent.k, seats, vEl.currentTime,
    { size: vCurrent.file.size, modified: vCurrent.file.lastModified }, $('seatComment').value);
  $('seatComment').value = '';
  saveSheet();
  renderSheet();
  renderSeatBar();
});
for (const ev of ['timeupdate', 'pause', 'play', 'seeked', 'loadedmetadata']) vEl.addEventListener(ev, () => renderMediaBars());

function renderMediaBars() { renderSeatBar(); renderCutBar(); renderVolBar(); }

// ---------- 上演中の動画の区間を直す（M3） ----------
// 止めた位置を「開始に／終わりに」入れて、修正票に video K を足す。切り直すのは作り手（編集アプリで。区間を定義ファイルに
// 持つ作品なら、その定義を直して）——プレイヤーは動画を変えない。⚠️ 元の区間（source_segments）は語り手の画面だけ（R1）

/** いまの動画が上演中の動画（role の無い動画）なら、その合図 */
function showCueOf(v) {
  const cue = v && v.kind !== 'link' && work && work.slides[v.n - 1] ? videoCueOf(work.slides[v.n - 1], v.k) : null;
  return cue && cue.role === undefined ? cue : null;
}
const cutItem = (v) => (sheet ? sheet.items.find((x) => x.kind === 'video' && x.slide === v.n && x.at === v.k) : null);

function renderCutBar() {
  const cue = showCueOf(vCurrent);
  const can = !!cue && !!sheet && editable(editCtx());
  $('cutBar').hidden = !can;
  if (!can) return;
  const at = vEl.currentTime || 0;
  const src = toSource(cue.source_segments, at);
  $('cutNow').textContent = t('cutNow', seatClock(at), src ? seatClock(src.at) : '');
  const x = cutItem(vCurrent);
  const end = (k) => (x && x[k] !== undefined ? seatClock(x[k]) : '—');
  $('cutSheet').textContent = x ? t('cutSheet', end('from'), end('to')) : t('cutHint');
  for (const id of ['cutFrom', 'cutTo']) {
    $(id).disabled = !vEl.paused;
    $(id).title = vEl.paused ? '' : t('cutPaused');
  }
}

function markHere(side) {
  if (!showCueOf(vCurrent) || !sheet || !editable(editCtx())) return;
  const c = $('cutComment').value.trim();
  sheet = markCut(sheet, work.slides[vCurrent.n - 1], vCurrent.k, side, vEl.currentTime,
    { size: vCurrent.file.size, modified: vCurrent.file.lastModified }, c ? c : undefined);
  $('cutComment').value = '';
  saveSheet();
  renderSheet();
  renderCutBar();
}
$('cutFrom').addEventListener('click', () => markHere('from'));
$('cutTo').addEventListener('click', () => markHere('to'));

// ---------- リンクの動画の音量を耳で直す ----------
// リンクの動画は YouTube の音のまま鳴り、動画ごとに大きさが違う（ブラウザからは測れない）。練習で流しながら「音を小さく・大きく」して、
// 決めた値を修正票（video K の Volume）へ。台本の volume へ書き戻すのは Claude。当日の動画のつまみ（全部の動画・その上演だけ）とは別。
// 上げられるのは YouTube の元の大きさ（0dB）まで——埋め込みは元より大きく鳴らせない。
// ⚠️ 修正票の値で鳴らすのは、練習（受付を開いていない）のあいだのこの端末だけ。受付を開いたら台本の値に戻す（聞き手の端末と同じ）

const VOL_STEP = 2; // dB。耳で「少し」と分かる幅

function renderVolBar() {
  const v = vCurrent;
  const isLinkNow = !!v && v.kind === 'link' && !!work && !!work.slides[v.n - 1];
  const can = isLinkNow && !!sheet && editable(editCtx());
  const slideData = isLinkNow ? work.slides[v.n - 1] : null;
  // この端末で鳴らす音量: 練習なら修正票の値、そうでなければ台本の値
  if (isLinkNow && linkP.item && linkP.item.id === v.id) linkP.setItemVolume(can ? linkVolumeNow(sheet, slideData, v.k) : v.volume);
  $('volBar').hidden = !can;
  if (!can) return;
  const db = linkVolumeNow(sheet, slideData, v.k);
  const was = v.volume || 0;
  $('volNow').textContent = db === was ? t('volNow', dbText(db)) : t('volChanged', dbText(db), dbText(was));
  $('volDown').disabled = db <= MIN_VOLUME_DB;
  $('volUp').disabled = db >= 0;
}

function stepVolume(dir) {
  const v = vCurrent;
  if (!v || v.kind !== 'link' || !sheet || !editable(editCtx())) return;
  const slideData = work.slides[v.n - 1];
  const db = Math.min(0, Math.max(MIN_VOLUME_DB, linkVolumeNow(sheet, slideData, v.k) + dir * VOL_STEP));
  sheet = setLinkVolume(sheet, slideData, v.k, db);
  saveSheet();
  renderSheet();
  renderVolBar();
}
$('volDown').addEventListener('click', () => stepVolume(-1));
$('volUp').addEventListener('click', () => stepVolume(1));

let board = null; // 開いている絵コンテ { id, cards: Map(n → 要素), probe, alive }

/** 要素のできごとを1回待つ（動画が読めなかったら false） */
function once(el, ev) {
  return new Promise((done) => {
    const ok = () => { el.removeEventListener('error', ng); done(true); };
    const ng = () => { el.removeEventListener(ev, ok); done(false); };
    el.addEventListener(ev, ok, { once: true });
    el.addEventListener('error', ng, { once: true });
  });
}

/** 絵コンテ: 席ごとのカード。カードの絵は、見えない2つ目の動画で各席の真ん中へ移って描く（写真を作品フォルダに足さない） */
async function openBoard() {
  const v = vCurrent;
  const seats = seatsOf(v);
  if (!seats) return;
  closeBoard();
  const host = $('board');
  const cards = new Map();
  const hint = Object.assign(document.createElement('p'), { className: 'muted hint', textContent: t('boardHint') });
  host.replaceChildren(hint, ...seats.map((s) => {
    const b = Object.assign(document.createElement('button'), { type: 'button', className: 'board-card', title: s.label || '' });
    const c = Object.assign(document.createElement('canvas'), { width: 192, height: 108 });
    const cap = document.createElement('span');
    cap.textContent = `${s.n} · ${seatClock(s.from)}${s.pin ? ' · 📌' : ''}`;
    b.append(c, cap);
    b.addEventListener('click', () => {
      if (!vEl.paused) vEl.pause();
      vEl.currentTime = (s.from + s.to) / 2; // カードの絵と同じ、席の真ん中（席の端はつなぎ目のフェードで前後の絵と重なる）
    });
    cards.set(s.n, b);
    return b;
  }));
  host.hidden = false;
  $('boardBtn').setAttribute('aria-expanded', 'true');
  const probe = Object.assign(document.createElement('video'), { muted: true, preload: 'auto', playsInline: true });
  probe.src = URL.createObjectURL(v.file);
  const me = { id: v.id, cards, probe, alive: true };
  board = me;
  renderMediaBars();
  if (!(await once(probe, 'loadeddata'))) return;
  for (const s of seats) {
    if (!me.alive) return;
    probe.currentTime = (s.from + s.to) / 2;
    if (!(await once(probe, 'seeked')) || !me.alive) return;
    const c = cards.get(s.n).querySelector('canvas');
    c.getContext('2d').drawImage(probe, 0, 0, c.width, c.height);
  }
}

function closeBoard() {
  if (board) {
    board.alive = false;
    URL.revokeObjectURL(board.probe.src);
    board.probe.removeAttribute('src');
    board.probe.load();
    board = null;
  }
  $('board').hidden = true;
  $('board').replaceChildren();
  $('boardBtn').setAttribute('aria-expanded', 'false');
}

function markBoard(now) {
  if (!board || !vCurrent || board.id !== vCurrent.id) return;
  for (const [n, el] of board.cards) {
    el.classList.toggle('on', pointedSeat(vCurrent, n));
    el.classList.toggle('now', !!now && now.n === n);
  }
}

$('boardBtn').addEventListener('click', () => (board ? closeBoard() : openBoard()));

function stopVideo() {
  clearInterval(tick);
  if (!vEl.paused) vEl.pause();
  if (!linkP.paused) linkP.pause();
  send(playVideo(session, 'stop', { now: Date.now() }));
  engine.duck(false);
  updateVoice();
  for (const [id, c] of calls) { calls.delete(id); c.close(); }
  renderPeers();
}

/** 予備: 保存で受け取れていない端末には、語り手の動画の映像をそのまま流す */
function streamTo(id) {
  const p = session.peers.get(id);
  // リンクの動画は各端末が自分で流す（この画面の映像は送らない。埋め込みの中身は取り出せない）
  if (!vCurrent || vCurrent.kind === 'link' || !peer || !p || p.status !== 'approved' || !p.plan || calls.has(id)) return;
  const x = p.plan.find((v) => v.id === vCurrent.id);
  const st = (xfer.get(id) || new Map()).get(vCurrent.id);
  if (x && x.mode === 'stored' && st && st.done) return; // 保存済みの端末は自分で再生する
  try {
    captured = captured || (vEl.captureStream ? vEl.captureStream() : vEl.mozCaptureStream());
  } catch (err) {
    console.error(err);
    return;
  }
  const call = peer.call(id, captured, { metadata: { video: vCurrent.id } });
  calls.set(id, call);
  call.on('close', () => { if (calls.get(id) === call) calls.delete(id); });
  renderPeers();
}

// ---------- 開演・BGM・効果音（段階4 P1・P3・P9） ----------

/** 語り手の端末の音を、いまの状態に合わせる。sounds＝その枚の効果音も鳴らすか */
function playHere(sounds) {
  if (!session.audio.started) return;
  engine.setBgm(astate(session.audio, Date.now()), (id) => audioUrls.get(id), gainOf);
  if (sounds) for (const f of soundsAt(work, session.slide)) engine.playSound(audioUrls.get(idOf(f)));
}

let audioTimer = 0;
async function doStartShow() {
  if (!work || session.audio.started) return;
  await engine.unlock(); // 押した操作の中で音を出せるようにする
  send(startShow(session, work, idOf, Date.now()));
  playHere(true);
  logWait(t('logStarted'));
  clock = clockStart(clock, Date.now());
  renderClock();
  for (const b of [$('startShow'), $('startShowBar')]) { b.disabled = true; b.textContent = t('started'); }
  clearInterval(audioTimer);
  audioTimer = setInterval(() => send(audioTick(session, Date.now())), TICK_MS);
  go({ type: 'started' }); // 受付の画面で押したら上演の画面へ
  updateVoice();
  await startTalk(); // 話しているあいだ BGM を下げる（練習でもマイクを開く）
}

// ---------- 語っているあいだ BGM を下げる（plans/kamishibai-player-talk-duck.md。2026-10-26） ----------
// 語り手の端末が自分のマイクの大きさを 0.05秒ごとに見て「話している」を決め（talkStep）、この端末の BGM を下げ、聞き手へ合図を送る。
// 録画は engine の master から取るので同じ下げ方が入る。⚠️ スピーカーで鳴らした BGM をマイクが拾うと、声と取り違える（語り手はイヤホン）
const TALK_KEY = 'dk-narrator-talk-duck';
let talk = { ctx: null, src: null, an: null, timer: 0, st: null, stream: null };
try { $('talkDuck').checked = localStorage.getItem(TALK_KEY) !== 'off'; } catch { /* 覚えられないブラウザ */ }
$('talkDuck').addEventListener('change', (e) => {
  try { localStorage.setItem(TALK_KEY, e.target.checked ? 'on' : 'off'); } catch { /* 同上 */ }
  if (!e.target.checked) setTalking(false);
});
function setTalking(on) {
  const was = !!(talk.st && talk.st.talking);
  talk.st = { ...(talk.st || {}), talking: !!on, since: null }; // 雑音の高さ（floor）は持ち越す
  if (was === !!on) return;
  applyTalk(!!on);
}
/** BGM を下げる／戻す・聞き手へ合図・画面の印 */
function applyTalk(on) {
  engine.talk(on);
  send(talkMessage(session, on));
  $('talkLamp').classList.toggle('off', !on);   // 場所は取ったまま（帯を折り返させない）
}
async function startTalk() {
  if (!session.audio.started) return;
  if (!mic) {
    mic = await getMic();
    if (mic) for (const tr of mic.getAudioTracks()) tr.enabled = voice.narratorMic;
    renderMicPick();
    renderVoiceButtons();
  }
  talkAttach();
}
/** いまのマイクに判定をつなぐ（マイクを選び直したら呼び直す） */
function talkAttach() {
  if (!mic || !session.audio.started) return;
  if (talk.stream === mic) return;
  try {
    if (!talk.ctx) talk.ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (talk.src) talk.src.disconnect();
    talk.src = talk.ctx.createMediaStreamSource(mic);
    talk.an = talk.ctx.createAnalyser();
    talk.an.fftSize = 1024;
    talk.src.connect(talk.an);
    talk.stream = mic;
  } catch { return; }
  const buf = new Float32Array(talk.an.fftSize);
  clearInterval(talk.timer);
  talk.timer = setInterval(() => {
    const live = $('talkDuck').checked && voice.narratorMic && !session.playback.playing;
    if (!live) { setTalking(false); return; }
    talk.an.getFloatTimeDomainData(buf);
    let sum = 0;
    for (const x of buf) sum += x * x;
    const db = 10 * Math.log10(sum / buf.length + 1e-12);
    const was = !!(talk.st && talk.st.talking);
    const next = talkStep(talk.st, db, performance.now());
    talk.st = next;
    if (next.talking !== was) applyTalk(next.talking);
  }, 50);
}
$('startShow').addEventListener('click', doStartShow);
$('startShowBar').addEventListener('click', doStartShow);

// 音のつまみは常時は要らないので畳んでおく（U4）
$('soundToggle').addEventListener('click', () => {
  const open = $('soundPanel').hidden;
  $('soundPanel').hidden = !open;
  $('soundToggle').setAttribute('aria-expanded', String(open));
});

$('muteLocal').addEventListener('change', (e) => engine.mute(!e.target.checked));

// ---------- 声（段階3 V1〜V11） ----------

/** 承認する（受付の一覧・知らせの帯・合い札で戻った端末で共通）。承認と同じ時に声の通話を張る（V2） */
function admit(id) {
  if (!joinedAt.has(id)) joinedAt.set(id, ++joinSeq);
  send(approve(session, id, work, pictures, sendableMedia(), Date.now()));
  startVoice(id);
}

function startMixer() {
  if (mixer) return;
  try {
    const AC = window.AudioContext || window.webkitAudioContext;
    actx = new AC(); // 「受付を始める」を押した操作の中なので、音を出せる
    mixer = createMixer(actx);
    if (mic) mixer.setNarrator(mic);
    mixer.setNarratorMic(voice.narratorMic);
    if (recorder) tapInto(mixer.tap()); // 練習で録り始めたあとに受付を開いた
  } catch (err) {
    console.error(err);
  }
  renderVoiceButtons();
}

/** 声の通話を張る（語り手 → 聞き手）。送るのは、その聞き手のための混ぜた声。聞き手はマイク（または無音）で答える */
function startVoice(id) {
  const p = session.peers.get(id);
  if (!peer || !mixer || !p || p.status !== 'approved') return;
  const old = voiceCalls.get(id);
  if (old) { voiceCalls.delete(id); old.close(); }
  const call = peer.call(id, mixer.output(id), { metadata: { kind: 'voice' } });
  if (!call) return;
  voiceCalls.set(id, call);
  call.on('stream', (stream) => {
    // 承認済みの端末からの声だけを混ぜる（R7）
    const q = session.peers.get(id);
    if (!q || q.status !== 'approved' || voiceCalls.get(id) !== call) return;
    mixer.input(id, stream);
    updateVoice();
  });
  call.on('close', () => { if (voiceCalls.get(id) === call) { voiceCalls.delete(id); if (mixer) mixer.drop(id, true); } });
}

function voiceCtx() {
  const a = session.audio.started ? astate(session.audio, Date.now()) : null;
  return { video: !!session.playback.playing, bgm: !!(a && a.id && a.playing) };
}

/** 誰の声を届けるかを決め直す（voice.js）。混ぜ合わせの栓と、聞き手への「届いているか」の合図 */
function updateVoice() {
  const ctx = voiceCtx();
  const r = routes(session.peers, voice, ctx);
  if (mixer) { mixer.setHeard(r.narrator); mixer.setNarratorTo(r.listeners); }
  send(voiceMessages(session.peers, voice, ctx, voicePrev));
  renderChips();
  renderVoiceButtons();
}

function renderVoiceButtons() {
  $('micSelf').textContent = voice.narratorMic ? t('micSelfOn') : t('micSelfOff');
  $('micSelf').classList.toggle('off', !voice.narratorMic);
  $('micSelf').disabled = !mic;
  $('voiceAll').textContent = voice.allHeld ? t('voiceAllHeld') : t('voiceAllOn');
  $('voiceAll').classList.toggle('off', voice.allHeld);
}

$('micSelf').addEventListener('click', () => {
  voice.narratorMic = !voice.narratorMic;
  if (mixer) mixer.setNarratorMic(voice.narratorMic);
  else if (mic) for (const tr of mic.getAudioTracks()) tr.enabled = voice.narratorMic; // 練習（受付なし）で録画しているとき
  updateVoice();
});
$('voiceAll').addEventListener('click', () => { voice.allHeld = !voice.allHeld; updateVoice(); });
$('bgmHold').addEventListener('change', (e) => { voice.bgmHold = e.target.checked; updateVoice(); });

// 話しているかの印（札の点）。札を描き直さず、点だけを動かす
setInterval(() => {
  if (!mixer) return;
  const lv = mixer.levels();
  for (const d of document.querySelectorAll('#chips [data-dot]')) d.classList.toggle('on', !!(lv[d.dataset.dot] && lv[d.dataset.dot].speaking));
}, 150);

// ---------- 音の点呼（V8・V9） ----------
// 端末を1台ずつ順に確かめの音を鳴らし、ほかの全端末のマイクが拾ったかを集める。
// ⚠️ 測るマイクはエコー除去・雑音抑制を切って取り直す（雑音抑制は一定の高さの音を消してしまう。エコー除去は自分が鳴らした音を消す）

const LISTEN_MS = 1400;
let round = 0;
const replies = new Map();         // round → Map(聞き手 id → level)

function gotHeard(id, h) {
  const m = replies.get(h.round);
  if (m) m.set(id, h.level);
}

async function rawMic() {
  return getMic(micWanted(), false); // 音の点呼は加工しない音で測る。マイクは選んだもの
}

// ---------- マイクを選ぶ（2026-10-26: カメラのマイクとヘッドセットのどちらで拾っているか分からなかった） ----------
// 選んだマイクはこの端末のブラウザに覚える（覚えられなくても既定で動く）。途中で選び直したら、届けている声と録画の両方を付け替える
const MIC_KEY = 'dk-narrator-mic';
let micTap = null; // 録画へつないだ語り手の声（外す関数）
function micWanted() {
  try { return localStorage.getItem(MIC_KEY) || ''; } catch { return ''; }
}
/** 選んだマイクを開く（開けなければ既定のマイク・それもだめなら null）。processed＝こだま消し・雑音消し・自動の音量合わせ */
async function getMic(id = micWanted(), processed = true) {
  const base = { echoCancellation: processed, noiseSuppression: processed, autoGainControl: processed };
  const open = (c) => navigator.mediaDevices.getUserMedia({ audio: c });
  try { return await open(id ? { ...base, deviceId: { exact: id } } : base); } catch { /* 外された・許可が無い */ }
  if (!id) return null;
  try { return await open(base); } catch { return null; }
}
const micLabelOf = (s) => (s && s.getAudioTracks()[0] ? s.getAudioTracks()[0].label : '');
async function renderMicPick() {
  const sel = $('micPick');
  let list = [];
  try { list = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === 'audioinput' && d.deviceId && !['default', 'communications'].includes(d.deviceId)); } catch { /* 使えないブラウザ */ }
  const opts = [['', t('micDefault')], ...list.map((d, i) => [d.deviceId, d.label || t('micN', i + 1)])];
  sel.replaceChildren(...opts.map(([v, l]) => Object.assign(document.createElement('option'), { value: v, textContent: l })));
  const want = micWanted();
  sel.value = opts.some(([v]) => v === want) ? want : '';
  $('micNow').textContent = mic ? t('micNow', micLabelOf(mic) || '?') : t('micNone');
  $('micSelf').title = mic ? micLabelOf(mic) : '';
}
$('micPick').addEventListener('change', async (e) => {
  try { localStorage.setItem(MIC_KEY, e.target.value); } catch { /* 同上 */ }
  if (!mic) { renderMicPick(); return; } // まだ使っていない: 次に開くときにこれを使う
  const next = await getMic(e.target.value);
  if (!next) { note(t('micFailed'), true); renderMicPick(); return; }
  for (const tr of mic.getAudioTracks()) tr.stop();
  mic = next;
  for (const tr of mic.getAudioTracks()) tr.enabled = (mixer || recorder) ? voice.narratorMic : false;
  if (mixer) { mixer.setNarrator(mic); mixer.setNarratorMic(voice.narratorMic); }
  if (recorder) { if (micTap) micTap(); micTap = recorder.addAudio(mic); }
  talkAttach();
  renderMicPick();
  renderVoiceButtons();
});
if (navigator.mediaDevices && navigator.mediaDevices.addEventListener) navigator.mediaDevices.addEventListener('devicechange', () => renderMicPick());
renderMicPick();

$('rollCall').addEventListener('click', async () => {
  if (!mixer) return;
  $('rollCall').disabled = true;
  $('rollResult').textContent = t('rollRunning');
  const results = [];
  const raw = voice.narratorMic ? await rawMic() : null;
  try {
    for (const source of rollOrder(session.peers)) {
      const r = ++round;
      const targets = [...session.peers.values()].filter((p) => p.status === 'approved' && p.view && p.view.mic === 'on').map((p) => p.id);
      replies.set(r, new Map());
      send(targets.map((id) => ({ to: id, msg: { t: 'listen', round: r, ms: LISTEN_MS } })));
      const mine = raw ? measure(actx, raw, LISTEN_MS) : Promise.resolve(null);
      await new Promise((res) => setTimeout(res, 300));
      if (source === 'narrator') beep(actx);
      else send([{ to: source, msg: { t: 'tone', round: r } }]);
      const narratorLevel = await mine;
      const t0 = Date.now();
      while (replies.get(r).size < targets.length && Date.now() - t0 < 2500) await new Promise((res) => setTimeout(res, 100));
      results.push({ source, levels: { narrator: narratorLevel, ...Object.fromEntries(replies.get(r)) } });
      replies.delete(r);
    }
  } finally {
    if (raw) for (const tr of raw.getTracks()) tr.stop();
  }
  const j = judgeRollCall(results, joinedAt);
  voice.sameRoom = new Set(j.hold);
  voice.quiet = new Set(j.quiet);
  const name = (id) => (id === 'narrator' ? t('rollNarrator') : who(session.peers.get(id)));
  const lines = [];
  if (j.speaker) lines.push(t('rollSpeaker'));
  for (const [a, b] of j.pairs) lines.push(t('rollPair', name(a), name(b)));
  // 聞くだけの端末も音を鳴らす（ハウリングを見つけるため）。止めるマイクが無い端末には「声を届けない」を言わない
  for (const id of j.hold) { const q = session.peers.get(id); if (q && q.view && q.view.mic === 'on') lines.push(t('rollHold', name(id))); }
  for (const id of j.quiet) lines.push(t('rollQuiet', name(id)));
  if (!lines.length) lines.push(t('rollClear', results.length));
  $('rollResult').textContent = lines.join('\n');
  $('rollResult').classList.toggle('error', j.speaker || j.pairs.length > 0);
  logWait(t('logRoll', lines.join(' / ')));
  $('rollCall').disabled = false;
  updateVoice();
});

// 当日の音量つまみ（音量の釣り合い L5）。語り手の端末にはすぐ、聞き手へは少しまとめて送る
let volTimer = 0;
function onVolume() {
  const music = Number($('volMusic').value) / 100;
  const video = Number($('volVideo').value) / 100;
  $('volMusicVal').textContent = `${$('volMusic').value}%`;
  $('volVideoVal').textContent = `${$('volVideo').value}%`;
  engine.setMusic(music);
  vEl.volume = video;
  linkP.volume = video;
  if (recorder) recorder.setVideoVolume(video);
  clearTimeout(volTimer);
  volTimer = setTimeout(() => send(setVolume(session, music, video)), 150);
}
$('volMusic').addEventListener('input', onVolume);
$('volVideo').addEventListener('input', onVolume);

// ---------- 録画と練習（G1〜G5・P1〜P4） ----------
// 録るのは「聞き手の画面」（絵か動画を 16:9 で描き直したもの）と全部の音。台本は録らない（R1）。
// 保存は語り手の PC の中だけ（R7）。録り始めるときに保存先を選び、録ったそばから少しずつ書く

/** 上演の画面の上の「練習中（受付を開いていません）」（P1） */
function renderPractice() {
  $('practiceNote').hidden = screen !== 'show' || !isPractice({ roomOpen: !!peer });
}

/** 経過時間（P3。本番でも出す）。全体と、この枚 */
function renderClock() {
  const c = clockRead(clock, Date.now());
  $('clock').textContent = c.total == null ? '' : t('clock', fmtTime(c.total), fmtTime(c.slide));
}
setInterval(renderClock, 500);

/** 録画の枠に描くもの（語り手の画面の「聞き手の画面」の枠と同じ決め方） */
function drawStage(put) {
  const img = $('current');
  const src = stageSource({
    // リンクの動画は録れない（埋め込みの映像は取り出せない）ので、その枚の絵を録る
    videoStarted: !!(vCurrent && vCurrent.kind !== 'link' && session.playback.id),
    videoReady: vEl.readyState >= 2 && vEl.videoWidth > 0,
    pictureReady: !!img.getAttribute('src') && img.complete && img.naturalWidth > 0,
  });
  if (src === 'video') put(vEl, vEl.videoWidth, vEl.videoHeight);
  else if (src === 'picture') put(img, img.naturalWidth, img.naturalHeight);
}

function tapInto(tap) {
  if (!recorder || !tap) return;
  const off = recorder.addAudio(tap.stream);
  recTaps.push(() => { off(); tap.close(); });
}

/** 保存先。⚠️ ?test のときだけ、保存先を選ぶ画面（ヘッドレスでは押せない）の代わりにこのページの専用の保存場所（OPFS）へ書く */
async function saveTarget(name) {
  if (TEST) {
    const dir = await navigator.storage.getDirectory();
    const h = await dir.getFileHandle(name, { create: true });
    window.__dkRecName = name;
    return h.createWritable();
  }
  const ext = recMime.ext;
  const h = await window.showSaveFilePicker({
    suggestedName: name,
    types: [{ description: ext.toUpperCase(), accept: { [recMime.mime.split(';')[0]]: ['.' + ext] } }],
  });
  return h.createWritable();
}

function renderRec() {
  const can = recordable({ hasWork: !!work, mime: recMime, canSave: TEST || typeof window.showSaveFilePicker === 'function' });
  const b = $('recBtn');
  b.disabled = !recorder && !can.ok;
  b.textContent = recorder ? t('recStop') : t('recStart');
  b.classList.toggle('rec', !!recorder);
  b.title = can.ok || recorder ? '' : t('recWhy_' + can.why);
  const info = $('recInfo');
  info.hidden = !recorder;
  if (recorder) {
    const st = recorder.status();
    info.textContent = t('recInfo', fmtTime(st.sec), fmtMB(st.bytes));
  }
}

let recBusy = false;
$('recBtn').addEventListener('click', async () => {
  if (recBusy) return;
  recBusy = true;
  try {
    if (recorder) await stopRecording();
    else await startRecording();
  } finally {
    recBusy = false;
    renderRec();
  }
});

async function startRecording() {
  if (!work || !recMime) return;
  // 押した操作の中で音の準備をしておく（保存先を選ぶ画面を閉じたあとでは、ブラウザが音を止めたままにすることがある）
  const r = createRecorder({ draw: drawStage });
  r.prepare();
  engine.unlock();
  let out;
  try {
    out = await saveTarget(recordName(work.title, new Date(), recMime.ext));
  } catch (err) {
    r.stop();
    if (!(err && err.name === 'AbortError')) note(t('recFailed', String((err && err.message) || err)), true);
    return; // 保存先を選ばなかった
  }
  // 練習（受付なし）では、マイクをまだ取っていない。語り手の声を録るためにここで取る（受付を開くときもこれを使う）
  if (!mic) {
    try {
      mic = await getMic();
      if (!mic) throw new Error('no mic');
      for (const tr of mic.getAudioTracks()) tr.enabled = voice.narratorMic;
    } catch { mic = null; }
    renderVoiceButtons();
  }
  recorder = r;
  recTaps = [];
  recorder.start(out, recMime.mime);
  if (mic) micTap = recorder.addAudio(mic);                 // 語り手の声（「自分のマイク: 切」なら無音）。マイクを選び直したら付け替える
  renderMicPick();
  tapInto(engine.tap());                                     // BGM・効果音
  if (mixer) tapInto(mixer.tap());                           // 届けている聞き手の声
  recorder.setVideoVolume(Number($('volVideo').value) / 100);
  if (!vEl.paused) recorder.setVideo(vEl);                   // 動画の途中から録り始めた
  send(setRecording(session, true));                         // 聞き手の全端末に「録画中」（G4）
  note(mic ? '' : t('recNoMic'), !mic);
  renderRec();
}

async function stopRecording() {
  const r = recorder;
  if (!r) return;
  send(setRecording(session, false));
  for (const off of recTaps.splice(0)) off();
  if (micTap) { micTap(); micTap = null; }
  recorder = null;
  renderRec();
  const res = await r.stop();
  note(res.error ? t('recFailed', res.error) : t('recSaved', fmtTime(res.sec), fmtMB(res.bytes)), !!res.error);
  window.__dkRecLast = res;
}

function note(text, bad) {
  $('recNote').hidden = !text;
  $('recNote').textContent = text;
  $('recNote').classList.toggle('error', !!bad);
}

// 録った時間と大きさ（G4）。書けなくなって録画が自分で止まったら、片付けて理由を出す
setInterval(() => {
  if (!recorder) return;
  if (!recorder.recording && !recBusy) { recBusy = true; stopRecording().finally(() => { recBusy = false; renderRec(); }); return; }
  renderRec();
}, 1000);

renderRec();

window.addEventListener('beforeunload', (e) => { if ((peer && approvedCount(session) > 0) || recorder) e.preventDefault(); });
// 画面を閉じるとき、聞き手に「終わり」を送る（届けば聞き手はすぐ気づく。届かないときは聞き手が接続の状態で気づく）
window.addEventListener('pagehide', () => {
  for (const conn of conns.values()) { try { if (conn.open) conn.send({ t: 'bye' }); } catch { /* 閉じかけ */ } }
});

renderVoiceButtons();

// 自動テスト用の入口（?test のときだけ。同じページの中からだけ呼べる。外から作品を渡す道ではない）
if (TEST) window.__dk = { link: () => ({ id: vCurrent && vCurrent.kind === 'link' ? vCurrent.id : null, ready: linkP.ready, error: linkP.error, stalled: linkP.stalled, playing: !linkP.paused, pos: linkP.currentTime, state: linkP.state(), captions: linkP.captionsNow(), vol: linkP.volumeNow(), note: $('videoNote').textContent }),
  // 語り手が YouTube の再生つまみを押したのと同じこと（埋め込みの中は外から押せないので、API の口から押す）
  linkPlayer: () => linkP,
  linkPress: (what, at) => { const p = linkP.p; if (what === 'play') p.playVideo(); else if (what === 'pause') p.pauseVideo(); else p.seekTo(at, true); return true; }, loadForTest: (w, files) => { work = validateWork(w).work; workMap = files; mediaMap = new Map(); sheet = loadSheet(work); return resolve(); }, session: () => session,
  reloadForTest: (w, files) => reloadWith({ work: validateWork(w).work, map: files }), sheet: () => sheet, editing: () => editing, screen: () => screen, voice: () => ({ heard: routes(session.peers, voice, voiceCtx()).narrator, levels: mixer ? mixer.levels() : {}, calls: [...voiceCalls.keys()], state: { ...voice, held: [...voice.held], sameRoom: [...voice.sameRoom], quiet: [...voice.quiet] }, narratorTo: mixer ? mixer.narratorGains() : {} }), audio: () => engine.state(), audioId: (f) => idOf(f),
  levels: () => audios.map((a) => ({ key: a.key, id: a.id, lufs: a.lufs ?? null, gain: a.gain ?? null })),
  rec: () => ({ on: !!recorder, mime: recMime, status: recorder ? recorder.status() : null, last: window.__dkRecLast || null, name: window.__dkRecName || null, recording: session.recording }),
  // 録ったファイル（OPFS）を base64 で少しずつ取り出す（確認スクリプトが ffprobe にかける）
  recChunk: async (off, len) => { const f = await (await (await navigator.storage.getDirectory()).getFileHandle(window.__dkRecName)).getFile();
    const b = new Uint8Array(await f.slice(off, off + len).arrayBuffer()); let s = ''; for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode(...b.subarray(i, i + 0x8000)); return { size: f.size, data: btoa(s) }; } };
