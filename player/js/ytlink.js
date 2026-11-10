// リンクの動画（YouTube。work-format §2.4・§3.3）。ファイルは誰の端末にも渡らず、各端末が埋め込みで流す。
// 上半分は DOM に触らない純粋な関数（node --test で守る）。下の LinkPlayer は YouTube IFrame Player API を包み、
// <video> と同じ形（currentTime・paused・play()・pause()・'play'/'pause'/'seeked'/'ended'/'error'）にする——
// 語り手の合図（playback.js）と聞き手の追従を、ファイルの動画と同じ道で通すため。

export const EMBED_ORIGIN = 'https://www.youtube-nocookie.com'; // クッキーを置かない埋め込み（CSP の frame-src）
export const API_URL = 'https://www.youtube.com/iframe_api';    // API の読み込み口（CSP の script-src）
const ID = /^[A-Za-z0-9_-]{11}$/;
const HOSTS = new Set(['youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtube-nocookie.com', 'www.youtube-nocookie.com', 'youtu.be']);

/** YouTube のリンクから動画の ID（11文字）。YouTube のリンクでなければ null。
 *  watch?v=・youtu.be/・embed/・shorts/・live/ を読む */
export function youtubeId(url) {
  let u;
  try { u = new URL(String(url)); } catch { return null; }
  if (u.protocol !== 'https:' && u.protocol !== 'http:') return null;
  if (!HOSTS.has(u.hostname.toLowerCase())) return null;
  const parts = u.pathname.split('/').filter(Boolean);
  let id = null;
  if (u.hostname.toLowerCase() === 'youtu.be') id = parts[0];
  else if (parts[0] === 'watch') id = u.searchParams.get('v');
  else if (['embed', 'shorts', 'live', 'v'].includes(parts[0])) id = parts[1];
  return id && ID.test(id) ? id : null;
}

/** 合図の動画がリンクか（file の代わりに url を持つ） */
export const isLink = (cue) => !!cue && cue.type === 'video' && typeof cue.url === 'string';

/** 流す範囲 { start, end }（秒）。end が無ければ動画の終わりまで（Infinity） */
export function cutOf(cue) {
  const start = Number.isFinite(cue && cue.start) ? Math.max(0, cue.start) : 0;
  const end = Number.isFinite(cue && cue.end) ? cue.end : Infinity;
  return { start, end };
}

/** 範囲の中に収める（頭出しで範囲の外へ出たとき） */
export const clampCut = (t, cut) => Math.min(Math.max(t, cut.start), cut.end);

/** 止める秒に着いたか（間隔をおいて見るので、少し手前で止める） */
export const END_EARLY = 0.15;
export const atEnd = (t, cut) => Number.isFinite(cut.end) && t >= cut.end - END_EARLY;

/** 頭出しを見つける（API には頭出しのできごとが無いので、位置の飛びで見る）。
 *  prev・cur = { t: 動画の秒, at: ミリ秒, playing } */
export const JUMP = 1.0;
export function jumped(prev, cur) {
  if (!prev || !cur) return false;
  if (prev.playing && cur.playing) return Math.abs(cur.t - (prev.t + (cur.at - prev.at) / 1000)) > JUMP;
  if (!prev.playing && !cur.playing) return Math.abs(cur.t - prev.t) > 0.05;
  return false;
}

/** 字幕の言語の書き方（ja・en・pt-BR など。BCP 47 の短い形） */
export const isCaptions = (v) => typeof v === 'string' && /^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$/.test(v);

/** リンクの動画1本の音量（work-format §2.4 の volume。dB、−40〜0）。書いていない・おかしい値は 0（そのまま） */
export const MIN_VOLUME_DB = -40;
export const isVolumeDb = (v) => typeof v === 'number' && Number.isFinite(v) && v >= MIN_VOLUME_DB && v <= 0;
export const volumeDbOf = (v) => (isVolumeDb(v) ? v : 0);

/** setVolume に渡す数（0〜100）。当日の動画のつまみ（0〜1）× その動画の音量（dB）。
 *  setVolume(n) は埋め込みの <video> の volume を n/100 にする（振幅に比例。2026-11-10 本物の YouTube で 0〜100 を測った）ので、
 *  −6dB は 50、−20dB は 10。⚠️ 整数しか渡せないので、つまみを下げて小さくすると段が粗くなる */
export function ytVolume(knob, db = 0) {
  const k = Math.min(1, Math.max(0, Number(knob) || 0));
  return Math.round(k * 10 ** (volumeDbOf(db) / 20) * 100);
}

/** 埋め込みの URL。関連動画は同じチャンネルのものだけ（rel=0）・キーボード操作なし（聞き手）・全画面のボタンなし（fs=0。
 *  全画面はプレイヤーの側で行う）。止める秒（end）は渡さない——渡すと止めたあとに YouTube が関連動画を並べるので、
 *  こちらで少し手前に止める（LinkPlayer）。origin は API の合図を受けるのに要る */
export function embedSrc(id, { start = 0, controls = true, origin = '', captions = null } = {}) {
  const q = new URLSearchParams({
    enablejsapi: '1', rel: '0', playsinline: '1', fs: '0', iv_load_policy: '3',
    controls: controls ? '1' : '0', disablekb: controls ? '0' : '1',
  });
  if (start > 0) q.set('start', String(Math.floor(start)));
  // 字幕を最初から出す（聞き手の端末にはつまみが無く、自分では選べない）。その言語の字幕が無い動画では出ない
  if (isCaptions(captions)) { q.set('cc_load_policy', '1'); q.set('cc_lang_pref', captions); }
  if (origin) q.set('origin', origin);
  return `${EMBED_ORIGIN}/embed/${id}?${q}`;
}

/** API の onError の番号 → 理由（i18n の linkWhy_<理由>） */
export function errorReason(code) {
  if (code === 101 || code === 150) return 'blocked';  // 所有者が埋め込みを禁じている
  if (code === 100) return 'gone';                     // 見つからない・非公開
  if (code === 2) return 'bad-link';
  if (code === 153) return 'referrer';                 // 埋め込み元が分からない（リファラーが届いていない）
  return 'player';                                     // 5（再生できない）など
}

// ---------- ここから下はブラウザの中だけ ----------

let api = null;
/** API を読む（1回だけ）。読めない端末（ネットが無い・遮られている）では、15秒で諦めて 'api' の理由で断る。
 *  ⚠️ 断られたら次に呼んだとき読み直す（一度の失敗で上演中ずっと使えなくしない） */
export function loadApi(timeout = 15000) {
  if (window.YT && window.YT.Player) return Promise.resolve(window.YT);
  if (!api) {
    api = new Promise((ok, ng) => {
      const timer = setTimeout(() => ng(new Error('api')), timeout);
      const prev = window.onYouTubeIframeAPIReady;
      window.onYouTubeIframeAPIReady = () => { clearTimeout(timer); if (typeof prev === 'function') prev(); ok(window.YT); };
      const s = document.createElement('script');
      s.src = API_URL;
      s.async = true;
      s.onerror = () => { clearTimeout(timer); s.remove(); ng(new Error('api')); };
      document.head.append(s);
    });
    api.catch(() => { api = null; });
  }
  return api;
}

const S = { UNSTARTED: -1, ENDED: 0, PLAYING: 1, PAUSED: 2, BUFFERING: 3, CUED: 5 };
export const STALL_MS = 10000;

/** 埋め込みの動画1本ぶんの再生口。host の中に iframe を作る。
 *  opts.follow＝聞き手（自分では動かさない。操作つまみなし・合図が止めているのに流れ始めたら止める） */
export class LinkPlayer extends EventTarget {
  constructor(host, { follow = false } = {}) {
    super();
    this.host = host;
    this.follow = follow;
    this.p = null;          // YT.Player
    this.item = null;       // { id, yt, start, end, captions, volume }
    this.cut = { start: 0, end: Infinity };
    this.ready = false;
    this.error = null;      // 流せない理由（errorReason か 'api'）
    this.playing = false;
    this.ended = false;
    this.started = false;   // 一度でも流れたか（流れるまでは位置を開始の秒とみなす）
    this.want = false;      // 聞き手: 合図が「流す」か
    this.pending = null;    // こちらからの頭出しが届くのを待っている { t, until }
    this.stalled = false;   // 再生を始めようとしたのに、STALL_MS たっても流れ始めない
    this.stallTimer = 0;
    this.hold = false;      // まだ流していない動画を頭出しした（YouTube が流し始めるので止め直す）
    this.vol = 1;
    this.last = null;       // 頭出しを見つけるための前回の位置
    this.timer = 0;
    this.gen = 0;
  }

  get paused() { return !this.playing; }

  get currentTime() {
    if (!this.p || !this.ready || typeof this.p.getCurrentTime !== 'function') return this.cut.start;
    // 一度も流していないあいだは、API は 0 を返す（読み込み中も）。流し始める位置（開始の秒）として扱う
    if (!this.started) return this.cut.start;
    return Number(this.p.getCurrentTime()) || 0;
  }

  set currentTime(t) {
    if (!this.p || !this.ready) return;
    const to = clampCut(Number(t) || 0, this.cut);
    this.ended = atEnd(to, this.cut) && this.ended;
    if (!this.started && to === this.cut.start) return; // 流し始める位置はもう開始の秒
    this.go(to);
    // ⚠️ まだ流していない動画を頭出しすると、YouTube は流し始める。止めておくべきなら止め直す（onState）
    if (!this.started && !this.want) this.hold = true;
  }

  /** こちらからの頭出し。届くまで（最長1.5秒）は位置の飛びを頭出しとみなさない——届く前の古い位置を拾うと、
   *  語り手の合図が一度古い位置へ戻る */
  go(to) {
    this.p.seekTo(to, true);
    this.pending = { t: to, until: performance.now() + 1500 };
  }

  set volume(v) {
    this.vol = Math.min(1, Math.max(0, Number(v)));
    // 当日のつまみ × この動画の音量（volume。読み込むたびに onReady で当て直す）
    if (this.p && this.ready && this.p.setVolume) this.p.setVolume(ytVolume(this.vol, this.item && this.item.volume));
  }

  /** いま読み込んでいる1本の音量（dB）を替える（練習で耳で直すとき。読み込み直さない） */
  setItemVolume(db) {
    if (!this.item || volumeDbOf(this.item.volume) === volumeDbOf(db)) return;
    this.item = { ...this.item, volume: volumeDbOf(db) };
    this.volume = this.vol;
  }

  /** 埋め込みに渡っている音量（0〜100。確かめ用） */
  volumeNow() {
    try { return this.p && this.p.getVolume ? this.p.getVolume() : null; } catch { return null; }
  }

  state() {
    try { return this.p && this.p.getPlayerState ? this.p.getPlayerState() : S.UNSTARTED; } catch { return S.UNSTARTED; }
  }

  /** 1本を読み込む（同じ1本なら何もしない）。読めた・読めなかったは 'ready'・'error' で知らせる */
  async load(item) {
    if (this.item && item && this.item.id === item.id && !this.error) return;
    this.unload();
    if (!item) return;
    const gen = ++this.gen;
    this.item = item;
    this.cut = cutOf(item);
    let YT;
    try { YT = await loadApi(); } catch { if (gen === this.gen) this.fail('api'); return; }
    if (gen !== this.gen) return;
    const frame = document.createElement('iframe');
    frame.src = embedSrc(item.yt, { start: this.cut.start, controls: !this.follow, origin: location.origin, captions: item.captions });
    frame.title = 'YouTube';
    frame.allow = 'autoplay; encrypted-media; picture-in-picture';
    // ⚠️ このプレイヤーのページはリファラーを送らない（_headers の no-referrer）。YouTube は埋め込み元が分からないと
    //    流さない（エラー 153）ので、この iframe だけ、どのサイトから開いたか（オリジンだけ・パスは送らない）を渡す
    frame.referrerPolicy = 'strict-origin-when-cross-origin';
    this.host.replaceChildren(frame);
    try {
      this.p = new YT.Player(frame, {
        events: {
          onReady: () => { if (gen !== this.gen) return; this.ready = true; this.volume = this.vol; this.watch(); this.emit('ready'); },
          onStateChange: (e) => { if (gen === this.gen) this.onState(e.data); },
          onError: (e) => { if (gen === this.gen) this.fail(errorReason(e.data)); },
        },
      });
    } catch (err) {
      console.error(err);
      this.fail('player');
    }
  }

  unload() {
    this.gen += 1;
    clearInterval(this.timer);
    this.timer = 0;
    if (this.p && this.p.destroy) { try { this.p.destroy(); } catch (err) { console.error(err); } }
    this.p = null;
    this.item = null;
    this.ready = false;
    this.error = null;
    this.playing = false;
    this.ended = false;
    this.started = false;
    this.captionsSet = false;
    this.want = false;
    this.hold = false;
    this.pending = null;
    this.stalled = false;
    clearTimeout(this.stallTimer);
    this.last = null;
    this.host.replaceChildren();
  }

  fail(reason) {
    this.error = reason;
    this.playing = false;
    this.emit('error');
  }

  /** 流す。流せたかどうかは 'play' で分かる（自動再生を止められた端末では来ない） */
  play() {
    this.want = true;
    this.hold = false;
    if (!this.p || !this.ready || this.error) return;
    if (this.ended || this.currentTime >= this.cut.end - END_EARLY) { this.go(this.cut.start); this.ended = false; }
    this.p.playVideo();
    this.trying();
  }

  pause() {
    this.want = false;
    clearTimeout(this.stallTimer);
    this.stallTimer = 0;
    if (this.p && this.ready && !this.error && this.state() !== S.PAUSED) this.p.pauseVideo();
  }

  /** 再生を始めようとした（YouTube が読み込みに入った）。STALL_MS のうちに流れ始めなければ 'stall'。
   *  ⚠️ 2026-11-09 ヘッドレスで、読み込み（3）のあと始まらない（-1）まま止まる動画があった（広告の読み込みの疑い・原因は未確定）。
   *  例外にはならないので、見張らないと語り手は気づけない */
  trying() {
    if (this.playing || this.stallTimer) return;
    this.stallTimer = setTimeout(() => {
      this.stallTimer = 0;
      if (this.playing || this.error) return;
      this.stalled = true;
      this.emit('stall');
    }, STALL_MS);
  }

  onState(st) {
    if (st === S.BUFFERING && !this.playing && !(this.follow && !this.want) && !this.hold) this.trying();
    if (st === S.PLAYING) {
      clearTimeout(this.stallTimer);
      this.stallTimer = 0;
      this.stalled = false;
      this.started = true;
      this.captionsOn();
      if (this.hold || (this.follow && !this.want)) { this.hold = false; this.p.pauseVideo(); return; }
      const was = this.playing;
      this.playing = true;
      if (this.currentTime < this.cut.start - JUMP) this.go(this.cut.start); // 開始より前へ戻した
      if (!was) { this.emit('play'); this.emit('playing'); }
    } else if (st === S.PAUSED || st === S.ENDED || st === S.CUED) {
      const was = this.playing;
      this.playing = false;
      if (was) this.emit('pause');
      if (st === S.ENDED && !this.ended) { this.ended = true; this.emit('ended'); } // 止める秒より先に動画が終わった
    }
    // BUFFERING（3）は流している途中の読み込み。流しているかどうかは変えない
  }

  /** 字幕の言語を選び直す。埋め込みの指定（cc_lang_pref）だけでは、別の言語や自動の字幕が出ることがあるので、
   *  流れ始めてから字幕の部品に言語を指定する。効かなくても（部品がまだ無い・その言語が無い）何もしない */
  captionsOn() {
    const lang = this.item && this.item.captions;
    if (!isCaptions(lang) || this.captionsSet || !this.p || typeof this.p.setOption !== 'function') return;
    try {
      if (typeof this.p.loadModule === 'function') this.p.loadModule('captions');
      this.p.setOption('captions', 'track', { languageCode: lang });
      this.captionsSet = true;
    } catch (err) {
      console.error(err);
    }
  }

  /** いま出している字幕の言語（分からなければ null。確かめ用） */
  captionsNow() {
    try {
      const tr = this.p && typeof this.p.getOption === 'function' ? this.p.getOption('captions', 'track') : null;
      return tr && tr.languageCode ? tr.languageCode : null;
    } catch {
      return null;
    }
  }

  /** 止める秒と頭出しを見張る（止めているあいだの頭出しも見る） */
  watch() {
    if (this.timer) return;
    this.last = { t: this.currentTime, at: performance.now(), playing: this.playing };
    this.timer = setInterval(() => {
      if (!this.p || !this.ready || !this.started) return;
      const cur = { t: this.currentTime, at: performance.now(), playing: this.playing };
      if (this.pending) {
        if (Math.abs(cur.t - this.pending.t) > 0.5 && cur.at < this.pending.until) return;
        this.pending = null;
        this.last = cur;
        return;
      }
      if (this.playing && atEnd(cur.t, this.cut) && !this.ended) {
        // 止める秒で止める（関連動画へ流れないように、終わりまで行かせない）
        this.ended = true;
        this.p.pauseVideo();
        this.emit('ended');
      } else if (jumped(this.last, cur)) {
        if (cur.t < this.cut.end - END_EARLY) this.ended = false;
        if (cur.t > this.cut.end) this.go(this.cut.end - END_EARLY);
        // 開始より前へ戻したら、開始へ戻す。⚠️ 戻さないと語り手だけ範囲の外を流し、聞き手は合図のたびに開始へ
        // 戻されて、開始の画面で固まって見えた（2026-11-09 実機で）
        else if (cur.t < this.cut.start - 0.5) this.go(this.cut.start);
        this.emit('seeked');
      }
      this.last = cur;
    }, 100);
  }

  emit(type) { this.dispatchEvent(new Event(type)); }
}
