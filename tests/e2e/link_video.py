"""リンクの動画（YouTube の埋め込み。work-format §2.4）を、語り手と離れた聞き手の2台で通す（Edge・ffmpeg が要る。
受付はインターネット上の紹介役を使う）:
    python tests/e2e/link_video.py [作業フォルダ]          # YouTube は読まない（API を差し替える。YouTube への通信は止める）
    python tests/e2e/link_video.py [作業フォルダ] --real   # 本物の YouTube で通す（ネットが要る。手で1回）
 見本の写しに、1枚目の BGM・2枚目のリンクの動画と [BGM after video]・3枚目にもう1本のリンクの動画を足す → 語り手が受付を開き、
別のブラウザの聞き手が入る → 開演 → 2枚目で語り手が再生・一時停止・頭出しをすると聞き手が付いてくる → 止める秒で両方とも止まる
（YouTube の「終わり」まで行かない）→ 動画で BGM が止まり、終わると after の曲 → 3枚目で、
差し替え版では「埋め込みを禁じられた動画」が語り手の画面に出る（--real では2本目も流れる）→ 例外が0件。
⚠️ 配るのは player/_headers の CSP・リファラーの決まりを当てた localhost（127.0.0.1 では、持ち主が埋め込みを
許していても YouTube が流さない動画がある——2026-11-09 実際に確かめた）。窓は出さない（見えないブラウザ）。
作業用リポジトリの見本は変えない（写しで行う）。"""
import argparse
import base64
import functools
import http.server
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for stream in (sys.stdout, sys.stderr):        # 日本語の Windows のコンソールでは出せない文字がある
    stream.reconfigure(encoding='utf-8', errors='backslashreplace')
ap = argparse.ArgumentParser()
ap.add_argument('here', nargs='?', help='作業フォルダ（写し）。無ければ一時フォルダ')
ap.add_argument('--real', action='store_true', help='本物の YouTube で通す')
args = ap.parse_args()
HERE = Path(args.here).resolve() if args.here else Path(tempfile.mkdtemp(prefix='dk-e2e-'))
HERE.mkdir(parents=True, exist_ok=True)
print(f'work: {HERE}  ({"本物の YouTube" if args.real else "YouTube を差し替え"})')
ROOT = HERE / 'link'
WORK = ROOT / 'sample'
sys.path.insert(0, str(REPO / 'skills' / 'digital-kamishibai' / 'scripts'))
import burn  # noqa: E402

# 触れる前の音・動画をブラウザが止めないように（聞き手の端末では、実機なら画面に触れたあと）
_real = subprocess.Popen
burn.subprocess = types.SimpleNamespace(Popen=lambda a, **kw: _real([a[0], '--autoplay-policy=no-user-gesture-required', *a[1:]], **kw),
                                        DEVNULL=subprocess.DEVNULL, TimeoutExpired=subprocess.TimeoutExpired)
BUILD = REPO / 'skills' / 'digital-kamishibai' / 'scripts' / 'build_work.py'
# 2本: TED とリオ（どちらも埋め込みを許している）。差し替え版では、2本目を「聞き手の端末でだけ流せない」にし、
# 3枚目に「どの端末でも流せない（埋め込みを禁じられた）」3本目を足す
FIRST = ('8KkKuTCFvzI', 351, 369)
SECOND = ('dCVlRFWOjgE', 45, 158)
BLOCKED = 'zzzzzzzzzz0'
STALL = 'yyyyyyyyyy0'   # 差し替え版で「押しても読み込みのまま始まらない」動画（広告・読み込みで止まった、の代わり）

failures = []


def ok(name, cond, detail=''):
    print(f'  {"OK " if cond else "NG "} {name}' + (f'  ({detail})' if detail else ''))
    if not cond:
        failures.append(name)


def ffmpeg(*a):
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', *map(str, a)], check=True)


# ---------- 準備: 見本の写し ----------
shutil.rmtree(ROOT, ignore_errors=True)
shutil.copytree(REPO / 'examples' / 'sample-story', WORK)
shutil.copytree(REPO / 'player', ROOT / 'player')
(WORK / 'sounds').mkdir(exist_ok=True)
ffmpeg('-f', 'lavfi', '-i', 'sine=frequency=330:duration=120', '-c:a', 'libmp3lame', WORK / 'sounds' / 'first.mp3')
ffmpeg('-f', 'lavfi', '-i', 'sine=frequency=550:duration=60', '-c:a', 'libmp3lame', WORK / 'sounds' / 'after.mp3')
script = (WORK / 'script.md').read_text(encoding='utf-8')
script = script.replace('## [Slide 1] Cover\n', '## [Slide 1] Cover\n\n> [BGM] sounds/first.mp3\n', 1)
script = script.replace('> [Picture] pictures/02.png\n',
                        '> [Picture] pictures/02.png\n\n> [BGM after video] sounds/after.mp3\n'
                        f'> [Video] https://www.youtube.com/watch?v={FIRST[0]} start {FIRST[1] // 60}:{FIRST[1] % 60:02d} end {FIRST[2]} captions ja\n', 1)
script = script.replace('> [Picture] pictures/03.png\n',
                        f'> [Picture] pictures/03.png\n\n> [Video] https://youtu.be/{SECOND[0]}?t={SECOND[1]} end {SECOND[2]}\n'
                        + ('' if args.real else f'> [Video] https://www.youtube.com/watch?v={BLOCKED}\n'
                                                f'> [Video] https://www.youtube.com/watch?v={STALL}\n'), 1)
(WORK / 'script.md').write_text(script, encoding='utf-8')
r = subprocess.run([sys.executable, str(BUILD), str(WORK), '--skip-text'], capture_output=True, text=True, encoding='utf-8', errors='replace')
ok('ビルドが通り、リンクの動画のファイルが無いことを警告しない', r.returncode == 0 and 'youtu' not in (r.stdout + r.stderr).lower(),
   (r.stdout + r.stderr).strip().splitlines()[-1] if (r.stdout + r.stderr).strip() else '')
w = json.loads((WORK / 'work.json').read_text(encoding='utf-8'))
ok('work.json にリンクと範囲が入る', w['slides'][1]['cues'][-1] == {'type': 'video', 'url': f'https://www.youtube.com/watch?v={FIRST[0]}', 'start': FIRST[1], 'end': FIRST[2], 'captions': 'ja'}
   and w['slides'][2]['cues'][0] == {'type': 'video', 'url': f'https://www.youtube.com/watch?v={SECOND[0]}', 'start': SECOND[1], 'end': SECOND[2]},
   json.dumps([w['slides'][1]['cues'], w['slides'][2]['cues']]))


# ---------- 配る: player/_headers を当てる ----------
HEADERS = {}
for line in (REPO / 'player' / '_headers').read_text(encoding='utf-8').splitlines():
    if line.startswith('  ') and ':' in line:
        k, v = line.strip().split(':', 1)
        HEADERS[k.strip()] = v.strip()


class Site(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, '.js': 'text/javascript', '.mjs': 'text/javascript'}

    def end_headers(self):
        for k, v in HEADERS.items():
            self.send_header(k, v)
        super().end_headers()

    def log_message(self, *a):
        pass


server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Site, directory=str(ROOT)))
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f'http://localhost:{server.server_address[1]}'
files = [{'url': '/' + p.relative_to(ROOT).as_posix(), 'rel': p.relative_to(ROOT).as_posix(), 'mtime': int(p.stat().st_mtime * 1000)}
         for p in WORK.rglob('*') if p.is_file()]
PICK = """(async (files) => {
  const list = [];
  for (const f of files) {
    const blob = await (await fetch(f.url, { cache: 'no-store' })).blob();
    const file = new File([blob], f.rel.split('/').pop(), { lastModified: f.mtime });
    Object.defineProperty(file, 'webkitRelativePath', { value: f.rel });
    list.push(file);
  }
  const input = document.getElementById('pickWork');
  Object.defineProperty(input, 'files', { value: list, configurable: true });
  input.dispatchEvent(new Event('change'));
  return true;
})"""
TRAP = ("window.__errs = []; addEventListener('error', (e) => __errs.push(e.message)); "
        "addEventListener('unhandledrejection', (e) => __errs.push(String(e.reason))); true")

# YouTube IFrame Player API の差し替え（ページの前に入れる）。時計で位置を進めるだけ。__ytBlocked の動画は onError 150
FAKE_YT = """(() => {
  const S = { UNSTARTED: -1, ENDED: 0, PLAYING: 1, PAUSED: 2, BUFFERING: 3, CUED: 5 };
  window.__ytBlocked = BLOCKED_LIST;
  const STALL_ID = 'STALL_ID_VALUE';
  class Player {
    constructor(el, opts) {
      this.ev = (opts && opts.events) || {};
      const u = new URL(el.src);
      this.id = u.pathname.split('/').pop();
      this.t = Number(u.searchParams.get('start') || 0); this.at = performance.now(); this.st = S.UNSTARTED;
      this.blocked = window.__ytBlocked.includes(this.id);
      setTimeout(() => { this.ev.onReady && this.ev.onReady({ target: this });
        if (this.blocked) setTimeout(() => this.ev.onError && this.ev.onError({ data: 150, target: this }), 30); }, 150);
    }
    now() { return this.st === S.PLAYING ? this.t + (performance.now() - this.at) / 1000 : this.t; }
    set(st) { this.t = this.now(); this.at = performance.now(); this.st = st;
      setTimeout(() => this.ev.onStateChange && this.ev.onStateChange({ data: st, target: this }), 0); }
    getCurrentTime() { return this.now(); }
    getPlayerState() { return this.st; }
    playVideo() { if (this.blocked || this.st === S.PLAYING) return; this.set(S.BUFFERING);
      if (this.id !== STALL_ID) setTimeout(() => this.set(S.PLAYING), 200); }
    pauseVideo() { if (this.st === S.PLAYING || this.st === S.BUFFERING) this.set(S.PAUSED); }
    seekTo(s) { this.t = s; this.at = performance.now(); if (this.st === S.UNSTARTED || this.st === S.CUED) this.playVideo(); }
    setVolume() {}
    destroy() {}
  }
  window.YT = { Player, PlayerState: S, loaded: 1 };
})();"""


def open_page(b, url, w, h, blocked=()):
    b.call('Emulation.setDeviceMetricsOverride', {'width': w, 'height': h, 'deviceScaleFactor': 1, 'mobile': False}, session=True)
    if not args.real:
        b.call('Network.enable', session=True)
        b.call('Network.setBlockedURLs', {'urls': ['*youtube.com*', '*youtube-nocookie.com*', '*ytimg.com*', '*googlevideo.com*']}, session=True)
        b.call('Page.addScriptToEvaluateOnNewDocument', {'source': FAKE_YT.replace('BLOCKED_LIST', json.dumps(list(blocked))).replace('STALL_ID_VALUE', STALL)}, session=True)
    b.call('Page.navigate', {'url': url}, session=True)
    time.sleep(1.5)
    b.evaluate(TRAP)


def shot(b, name):
    (HERE / name).write_bytes(base64.b64decode(b.call('Page.captureScreenshot', {'format': 'png'}, session=True)['data']))


def wait(b, js, what, tries=400, step=0.05):
    for _ in range(tries):
        try:
            if b.evaluate(js):
                return True
        except burn.BurnError:
            pass
        time.sleep(step)
    print('  timeout: ' + what)
    return False


exe = burn.find_browser()
nar, lis = burn.Browser(exe), burn.Browser(exe)
try:
    open_page(nar, base + '/player/narrator.html?test', 1600, 1100, [BLOCKED])
    nar.evaluate(f"localStorage.clear(); {PICK}({json.dumps(files)})")
    wait(nar, "document.getElementById('workTitle').textContent.length > 0", 'work')
    ok('語り手の準備の画面に「YouTube に届かない」が出ない', nar.evaluate("document.getElementById('linkWarn').hidden"))
    nar.evaluate("document.querySelector('[data-goto=room]').click(); document.getElementById('expected').value = 1; "
                 "document.getElementById('openRoom').click(); true")
    ok('受付が開く', wait(nar, "/\\d/.test(document.getElementById('code').textContent)", 'code', 600))
    code = nar.evaluate("document.getElementById('code').textContent").replace(' ', '')
    open_page(lis, base + '/player/listen.html?test', 900, 506, [SECOND[0], BLOCKED])
    lis.evaluate(f"document.getElementById('code').value = '{code}'; document.getElementById('name').value = 'far'; "
                 "document.querySelector('input[name=mic][value=listen]').checked = true; "
                 "document.getElementById('joinForm').requestSubmit(); true")
    wait(nar, "document.querySelectorAll('#requests button').length > 0", 'request', 600)
    nar.evaluate("document.querySelector('#requests button').click(); true")
    ok('聞き手に1枚目の絵が出る', wait(lis, "!document.getElementById('picture').hidden && document.getElementById('picture').naturalWidth > 0", 'picture', 600))
    nar.evaluate("document.querySelector('[data-goto=show]').click(); true")
    time.sleep(0.3)
    nar.evaluate("document.getElementById('startShowBar').click(); true")
    ok('開演で1枚目の BGM が鳴る', wait(nar, "__dk.audio().playing", 'bgm'))

    # ---- 2枚目: リンクの動画 ----
    nar.evaluate("document.getElementById('nextBtn').click(); true")
    ok('語り手の枠に埋め込みが読み込まれる', wait(nar, "__dk.link().ready", 'narrator ready', 600), json.dumps(nar.evaluate("__dk.link()")))
    ok('聞き手も、流す前に読み込んでおく（まだ見せない＝絵のまま）',
       wait(lis, "__dkl.link().ready && !__dkl.link().on && !document.getElementById('picture').hidden", 'listener ready', 600),
       json.dumps(lis.evaluate("__dkl.link()")))
    ok('前の曲は止まっている（[BGM after video] の枚）', not nar.evaluate("__dk.audio().playing"))

    def both():
        return nar.evaluate("__dk.link()"), lis.evaluate("__dkl.link()")

    nar.evaluate("__dk.linkPress('play')")
    ok('再生: 聞き手が見せて流し始める', wait(lis, "__dkl.link().on && __dkl.link().playing", 'listener plays', 400), json.dumps(both()))
    time.sleep(3)
    n, l = both()
    ok('再生: 位置がそろう（1.5秒以内）', n['playing'] and l['playing'] and abs(n['pos'] - l['pos']) < 1.5, f"{n['pos']:.2f} / {l['pos']:.2f}")
    ok('再生: 聞き手の画面は絵から動画に替わる', lis.evaluate("document.getElementById('picture').hidden"))
    ok('字幕: 聞き手の埋め込みに、日本語の字幕を最初から出す指定が入る',
       lis.evaluate("document.querySelector('#llinkFrame iframe').src.includes('cc_lang_pref=ja')"))
    if args.real:
        ok('字幕: 聞き手の端末で日本語の字幕が出ている', wait(lis, "__dkl.link().captions === 'ja'", 'captions', 100),
           json.dumps(lis.evaluate('__dkl.link()')))
    ok('再生: 聞き手の札は「動画」', wait(nar, "[...document.querySelectorAll('#chips .chip')].some((c) => c.dataset.level === 'ok')", 'chip ok', 100),
       nar.evaluate("document.getElementById('chips').textContent"))

    nar.evaluate("__dk.linkPress('pause')")
    ok('一時停止: 聞き手も止まる', wait(lis, "!__dkl.link().playing", 'listener pause', 100))
    time.sleep(0.8)
    n, l = both()
    ok('一時停止: 止まった位置がそろう（0.3秒以内）', abs(n['pos'] - l['pos']) < 0.3, f"{n['pos']:.2f} / {l['pos']:.2f}")

    to = FIRST[1] + 9
    nar.evaluate(f"__dk.linkPress('seek', {to})")
    ok('止めたまま頭出し: 聞き手も同じ位置へ', wait(lis, f"Math.abs(__dkl.link().pos - {to}) < 0.3 && !__dkl.link().playing", 'listener seek', 200),
       json.dumps(both()))
    # 開始より前へ戻すと、語り手も開始へ戻る（語り手だけ範囲の外を流すと、聞き手は開始の画面で固まった——2026-11-09 実機で）
    nar.evaluate(f"__dk.linkPress('seek', {FIRST[1] - 20})")
    time.sleep(1.5)
    ok('開始より前へ頭出し: 語り手も聞き手も開始の位置へ戻る', wait(nar, f"Math.abs(__dk.link().pos - {FIRST[1]}) < 0.5", 'narrator back to start', 100)
       and wait(lis, f"Math.abs(__dkl.link().pos - {FIRST[1]}) < 0.5", 'listener at start', 100), json.dumps(both()))
    nar.evaluate(f"__dk.linkPress('seek', {to})")
    wait(lis, f"Math.abs(__dkl.link().pos - {to}) < 0.3", 'listener seek back', 200)
    nar.evaluate("__dk.linkPress('play')")
    wait(lis, "__dkl.link().playing", 'listener plays again', 200)
    time.sleep(1.5)
    to = FIRST[1] + 3
    nar.evaluate(f"__dk.linkPress('seek', {to})")
    time.sleep(2.5)
    n, l = both()
    ok('流しながら頭出し（戻す）: 聞き手も付いてくる', n['playing'] and l['playing'] and abs(n['pos'] - l['pos']) < 1.5 and n['pos'] < FIRST[1] + 8,
       f"{n['pos']:.2f} / {l['pos']:.2f}")
    to = FIRST[2] - 4
    nar.evaluate(f"__dk.linkPress('seek', {to})")
    ok('止める秒で、語り手が止まる', wait(nar, "!__dk.link().playing", 'narrator stops', 300), json.dumps(both()))
    ok('止める秒で、聞き手も止まる', wait(lis, "!__dkl.link().playing", 'listener stops', 100), json.dumps(both()))
    time.sleep(1.0)
    n, l = both()
    ok('止めた位置は止める秒の手前（0.5秒以内）・YouTube の「終わり」まで行かない（関連動画が出ない）',
       FIRST[2] - 0.5 <= n['pos'] <= FIRST[2] and FIRST[2] - 0.5 <= l['pos'] <= FIRST[2] and n['state'] != 0 and l['state'] != 0,
       f"{n['pos']:.2f}（{n['state']}） / {l['pos']:.2f}（{l['state']}）")
    ok('止めたあと、聞き手が頭から流し直さない', not lis.evaluate("__dkl.link().playing"))
    ok('動画が終わると [BGM after video] の曲が鳴る（語り手）', wait(nar, "__dk.audio().playing && __dk.audio().bgm === __dk.audioId('sounds/after.mp3')", 'after bgm', 100),
       json.dumps(nar.evaluate("__dk.audio()")))
    ok('聞き手にも after の曲の合図が届く', wait(lis, "__dkl.audio().bgm != null && __dkl.audio().playing", 'listener after bgm', 200),
       json.dumps(lis.evaluate("__dkl.audio()")))

    # ---- 3枚目: 2本目 ----
    nar.evaluate("document.getElementById('nextBtn').click(); true")
    ok('枚を移ると、聞き手は埋め込みを下げて絵に戻る', wait(lis, "!__dkl.link().on && !document.getElementById('picture').hidden", 'listener back to picture', 200))
    if args.real:
        ok('2本目も語り手の枠で読み込める', wait(nar, "__dk.link().ready && !__dk.link().error", 'second ready', 600), json.dumps(nar.evaluate("__dk.link()")))
        nar.evaluate("__dk.linkPress('play')")
        played = wait(lis, "__dkl.link().on && __dkl.link().playing", 'second plays', 600)
        if not played:
            # ⚠️ ヘッドレスでは、語り手のページで1本目を流したあとの2本目が、読み込みのまま始まらなかった（毎回。単独なら流れる。
            #    原因は未確定）。2026-11-09 の実機（PC の Chrome＋スマートフォン）では同じ順で始まった——ここが NG でも、実機で見る
            shot(nar, 'link_second_narrator.png')   # 広告・YouTube の案内が出ていないか、あとで目で見る
            ok('（始まらなかったとき）語り手の枠の下に「始まらない」が出る', wait(nar, "__dk.link().stalled", 'stall note', 300),
               nar.evaluate("document.getElementById('videoNote').textContent"))
        ok('2本目: 聞き手が付いてくる', played, json.dumps(both()))
        nar.evaluate(f"__dk.linkPress('seek', {SECOND[2] - 3})")
        ok('2本目: 止める秒で両方止まる', wait(nar, "!__dk.link().playing", 'second stops', 300) and wait(lis, "!__dkl.link().playing", 'second listener stops', 100),
           json.dumps(both()))
    else:
        # 2本目: 語り手の端末では流せるが、聞き手の端末では流せない（その端末だけ YouTube に届かない、などの代わり）
        ok('聞き手の端末で流せないことが、語り手の枠の下・一覧・札に出る（押す前に分かる）',
           wait(nar, "__dk.link().ready && !__dk.link().error && document.getElementById('videoNote').classList.contains('bad') && "
                     "document.getElementById('listeners').textContent.includes('YouTube') && "
                     "[...document.querySelectorAll('#chips .chip')].some((c) => c.dataset.level === 'warn')", 'peer blocked', 200),
           nar.evaluate("document.getElementById('videoNote').textContent + ' ／ ' + document.getElementById('listeners').textContent"))
        nar.evaluate("__dk.linkPress('play')")
        wait(nar, "__dk.link().playing", 'narrator plays the second', 100)
        ok('語り手が流しても、流せない聞き手は絵のまま、わけを1行出す',
           wait(lis, "!__dkl.link().on && !document.getElementById('picture').hidden && "
                     "document.getElementById('status').textContent.length > 0", 'listener reason', 100),
           lis.evaluate("document.getElementById('status').textContent"))
        nar.evaluate("__dk.linkPress('pause')")
        # 3本目: どの端末でも流せない（埋め込みを禁じられた）。1枚に2本あるので、語り手が選ぶ
        nar.evaluate("document.querySelectorAll('#videoPick button')[1].click(); true")
        ok('埋め込みを禁じられた動画: 語り手の枠の下に、流せないこと・わけ・流せないときの語りへ進むことが出る',
           wait(nar, "__dk.link().error === 'blocked' && document.getElementById('videoNote').textContent.includes('語り')", 'narrator blocked', 200),
           nar.evaluate("document.getElementById('videoNote').textContent"))
        ok('動画を選び直すと、聞き手は絵に戻る', wait(lis, "!__dkl.link().on && !document.getElementById('picture').hidden", 'listener picture', 100))
        # 4本目: 押しても読み込みのまま始まらない（広告・読み込みで止まった）。例外にはならないので、見張って語り手に出す
        nar.evaluate("document.querySelectorAll('#videoPick button')[2].click(); true")
        wait(nar, "__dk.link().ready", 'stall ready', 200)
        nar.evaluate("__dk.linkPress('play')")
        ok('始まらない動画: 10秒で、語り手の枠の下に「始まらない・押し直すか流せないときの語りへ」が出る',
           wait(nar, "__dk.link().stalled && document.getElementById('videoNote').classList.contains('bad')", 'narrator stall', 300),
           nar.evaluate("document.getElementById('videoNote').textContent"))
    nar.evaluate("document.getElementById('nextBtn').click(); true")
    time.sleep(1.0)
    ok('語り手・聞き手のページに例外が0件', nar.evaluate("window.__errs.length") == 0 and lis.evaluate("window.__errs.length") == 0,
       json.dumps([nar.evaluate("window.__errs"), lis.evaluate("window.__errs")]))
finally:
    nar.close()
    lis.close()
    server.shutdown()

print('ALL OK' if not failures else f'NG {len(failures)}: ' + ' / '.join(failures))
sys.exit(1 if failures else 0)
