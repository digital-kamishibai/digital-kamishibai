"""リンクの動画の音量を、練習で耳で直す1往復をまるごと通す（Edge が要る。YouTube は読まない——API を差し替える）:
    python tests/e2e/link_volume.py [作業フォルダ]
 見本の写しの3枚目に、volume -4dB のリンクの動画を足して練習用に組む → 語り手の画面で「この動画の音を小さく／大きく」→
埋め込みに渡る音量（setVolume）がその場で替わる・0dB（元の大きさ）より上へは行かない・台本の値に戻すと件が消える →
修正票に video K の Volume → check_sheet は PENDING → 台本の volume を書き替えて組み直し、作品を読み直す → 反映済みで消える →
受付を開くと、ボタンは消え、音量は台本の値。作業用リポジトリの見本は変えない（写しで行う）。"""
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
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ap = argparse.ArgumentParser()
ap.add_argument('here', nargs='?', help='作業フォルダ（写し）。無ければ一時フォルダ')
args = ap.parse_args()
for stream in (sys.stdout, sys.stderr):        # 日本語の Windows のコンソールでは出せない文字がある
    stream.reconfigure(encoding='utf-8', errors='backslashreplace')
HERE = Path(args.here).resolve() if args.here else Path(tempfile.mkdtemp(prefix='dk-e2e-'))
HERE.mkdir(parents=True, exist_ok=True)
print(f'work: {HERE}')
WORK = HERE / 'rt' / 'work'
PY = sys.executable
sys.path.insert(0, str(REPO / 'skills' / 'digital-kamishibai' / 'scripts'))
import burn  # noqa: E402

BUILD = REPO / 'skills' / 'digital-kamishibai' / 'scripts' / 'build_work.py'
CHECK = REPO / 'skills' / 'digital-kamishibai' / 'scripts' / 'check_sheet.py'
LINE = '> [Video] https://www.youtube.com/watch?v=8KkKuTCFvzI start 5:51 end 6:09'
N, K = 3, 1

failures = []


def ok(name, cond, detail=''):
    print(f'  {"OK " if cond else "NG "} {name}' + (f'  ({detail})' if detail else ''))
    if not cond:
        failures.append(name)


def run(*a):
    r = subprocess.run([PY, *map(str, a)], capture_output=True, text=True, encoding='utf-8', errors='replace')
    print(f'$ {Path(str(a[0])).name} {" ".join(map(str, a[1:]))}  -> {r.returncode}')
    for line in (r.stdout + r.stderr).strip().splitlines()[-4:]:
        print('    ' + line)
    return r


# ---------- 準備: 見本の写し ----------
shutil.rmtree(HERE / 'rt', ignore_errors=True)
shutil.copytree(REPO / 'examples' / 'sample-story', WORK)
script = WORK / 'script.md'
text = script.read_text(encoding='utf-8')
script.write_text(text.replace('> [Picture] pictures/03.png\n', f'> [Picture] pictures/03.png\n\n{LINE} volume -4dB\n', 1), encoding='utf-8')
assert run(BUILD, WORK, '--draft', '--skip-text').returncode == 0
shutil.copytree(REPO / 'player', HERE / 'rt' / 'site' / 'player')


class Quiet(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, '.js': 'text/javascript', '.mjs': 'text/javascript'}

    def log_message(self, *a):
        pass


server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(HERE / 'rt')))
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f'http://127.0.0.1:{server.server_address[1]}'


def listing():
    return [{'url': '/' + p.relative_to(HERE / 'rt').as_posix(), 'rel': p.relative_to(WORK.parent).as_posix(),
             'mtime': int(p.stat().st_mtime * 1000)} for p in WORK.rglob('*') if p.is_file()]


PICK = """(async (inputId, files) => {
  const list = [];
  for (const f of files) {
    const blob = await (await fetch(f.url, { cache: 'no-store' })).blob();
    const file = new File([blob], f.rel.split('/').pop(), { lastModified: f.mtime });
    Object.defineProperty(file, 'webkitRelativePath', { value: f.rel });
    list.push(file);
  }
  const input = document.getElementById(inputId);
  Object.defineProperty(input, 'files', { value: list, configurable: true });
  input.dispatchEvent(new Event('change'));
  return true;
})"""
SHEET = """(async () => {
  const m = await import('/site/player/js/corrections.js');
  const key = Object.keys(localStorage).find(k => k.startsWith('dk-corrections:'));
  return key ? m.sheetMarkdown(JSON.parse(localStorage.getItem(key)), new Date(2026, 10, 10, 20, 0)) : '';
})()"""
# YouTube IFrame Player API の差し替え（link_video.py と同じ形の小さい版）。setVolume で渡された数を持つだけ
FAKE_YT = """(() => {
  class Player {
    constructor(el, opts) {
      this.ev = (opts && opts.events) || {}; this.st = -1; this.vol = 100;
      this.t = Number(new URL(el.src).searchParams.get('start') || 0);
      setTimeout(() => this.ev.onReady && this.ev.onReady({ target: this }), 100);
    }
    set(st) { this.st = st; setTimeout(() => this.ev.onStateChange && this.ev.onStateChange({ data: st, target: this }), 0); }
    getCurrentTime() { return this.t; }
    getPlayerState() { return this.st; }
    playVideo() { this.set(1); }
    pauseVideo() { this.set(2); }
    seekTo(s) { this.t = s; }
    setVolume(n) { this.vol = n; }
    getVolume() { return this.vol; }
    destroy() {}
  }
  window.YT = { Player, PlayerState: { UNSTARTED: -1, ENDED: 0, PLAYING: 1, PAUSED: 2, BUFFERING: 3, CUED: 5 }, loaded: 1 };
})()"""

b = burn.Browser(burn.find_browser())
ev = b.evaluate


def wait(js, what, tries=400):
    for _ in range(tries):
        try:
            if ev(js):
                return True
        except burn.BurnError:
            pass
        time.sleep(0.05)
    print('  timeout: ' + what)
    return False


def click(id_, times=1):
    for _ in range(times):
        ev(f"document.getElementById('{id_}').click(); true")
        time.sleep(0.1)


def shot(name):
    (HERE / name).write_bytes(base64.b64decode(b.call('Page.captureScreenshot', {'format': 'png'}, session=True)['data']))


vol = lambda: ev("__dk.link().vol")
bar = lambda: ev("document.getElementById('volNow').textContent")

try:
    b.call('Emulation.setDeviceMetricsOverride', {'width': 1600, 'height': 1300, 'deviceScaleFactor': 1, 'mobile': False}, session=True)
    b.call('Network.enable', session=True)
    b.call('Network.setBlockedURLs', {'urls': ['*youtube.com*', '*youtube-nocookie.com*', '*ytimg.com*', '*googlevideo.com*']}, session=True)
    b.call('Page.addScriptToEvaluateOnNewDocument', {'source': FAKE_YT}, session=True)
    b.call('Page.navigate', {'url': base + '/site/player/narrator.html?test'}, session=True)
    wait("!!document.getElementById('pickWork')", 'page')
    time.sleep(0.5)
    ev("localStorage.clear(); window.__errs = []; addEventListener('error', (e) => __errs.push(e.message)); "
       "addEventListener('unhandledrejection', (e) => __errs.push(String(e.reason))); true")

    # ---------- 1. 練習: 流しながら音を小さく・大きく ----------
    ev(f"{PICK}('pickWork', {json.dumps(listing())})")
    wait("document.getElementById('workTitle').textContent.length > 0", 'work loaded')
    ev("document.querySelector('[data-goto=show]').click(); true")
    for _ in range(N - 1):
        click('nextBtn')
    ok('埋め込みが読み込まれる', wait("__dk.link().ready", 'link ready'))
    ok('音量のバーが出る（練習・リンクの動画）', not ev("document.getElementById('volBar').hidden"))
    ok('はじめは台本の値（-4dB → setVolume(63)）', vol() == 63 and '-4dB' in bar(), f'{vol()} / {bar()}')
    ok('区間のバーは出ない（リンクの動画）', ev("document.getElementById('cutBar').hidden"))
    ev("__dk.linkPress('play')")
    time.sleep(0.2)
    click('volDown', 3)
    ok('流しながら小さく×3 → -10dB（setVolume(32)）', vol() == 32 and '-10dB' in bar() and '-4dB' in bar(), f'{vol()} / {bar()}')
    click('volUp', 6)
    ok('大きく×6 → 0dB で止まる（元より大きくはしない）', vol() == 100 and ev("document.getElementById('volUp').disabled"), f'{vol()} / {bar()}')
    click('volDown', 2)
    ok('台本の値に戻すと、修正票の件が消える', vol() == 63 and ev(SHEET) == '', repr(ev(SHEET)))
    click('volDown', 1)
    ok('小さく → -6dB（setVolume(50)）', vol() == 50, str(vol()))
    shot('volume_bar.png')
    md = ev(SHEET)
    print('   修正票:\n' + '\n'.join('     ' + line for line in md.strip().splitlines()))
    ok('修正票に video K の Volume', md.strip().split('\n\n', 1)[1].splitlines() == [f'## [Slide {N}] video {K}', 'Volume -6dB (was -4dB)'])
    sheet = HERE / 'rt' / 'sheet.md'
    sheet.write_text(md, encoding='utf-8')

    # ---------- 2. 書き戻す前は PENDING・書き戻すと done ----------
    r = run(CHECK, WORK, sheet)
    ok('check_sheet: 書き戻す前は PENDING', r.returncode == 1 and f'PENDING   [Slide {N}] video {K}' in r.stdout)
    script.write_text(script.read_text(encoding='utf-8').replace(f'{LINE} volume -4dB', f'{LINE} volume -6dB'), encoding='utf-8')
    r = run(CHECK, WORK, sheet)
    ok('check_sheet: 台本の volume を書き替えると done', r.returncode == 0 and f'done      [Slide {N}] video {K}' in r.stdout)
    assert run(BUILD, WORK, '--draft', '--skip-text').returncode == 0

    # ---------- 3. 作品を読み直す: 反映済みで消える・音量は台本の新しい値 ----------
    ev(f"{PICK}('reloadWork', {json.dumps(listing())})")
    wait("document.getElementById('reloadNote').textContent.length > 0", 'reloaded')
    print('   読み直し:', ev("document.getElementById('reloadNote').textContent"))
    ok('読み直すと、反映済みの件は消える', ev("Object.keys(localStorage).filter(k => k.startsWith('dk-corrections:')).length") == 0)
    wait("__dk.link().ready", 'link ready again')
    ok('音量は台本の新しい値（-6dB → 50）', vol() == 50 and '-6dB' in bar(), f'{vol()} / {bar()}')

    # ---------- 4. 受付を開くと、ボタンは消え、音量は台本の値 ----------
    click('volDown', 2)
    ok('もう一度練習で小さく → -10dB（32）', vol() == 32, str(vol()))
    ev("document.querySelector('[data-goto=room]').click(); document.getElementById('expected').value = 1; "
       "document.getElementById('openRoom').click(); true")
    wait("/\\d/.test(document.getElementById('code').textContent)", 'room', 600)
    ev("document.querySelector('[data-goto=show]').click(); true")
    time.sleep(0.3)
    ok('受付を開くと、音量のバーは消える', ev("document.getElementById('volBar').hidden"))
    ok('受付を開くと、台本の値で鳴らす（聞き手と同じ。50）', vol() == 50, str(vol()))

    errs = ev("window.__errs")
    ok('ページの例外が0件', not errs, str(errs))
finally:
    b.close()
    server.shutdown()

print('ALL OK' if not failures else f'NG {len(failures)}: ' + ' / '.join(failures))
sys.exit(1 if failures else 0)
