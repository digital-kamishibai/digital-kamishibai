"""大きすぎる BGM を、語り手の端末でも聞き手の端末でも小さくして鳴らすことを確かめる（2台。Edge・ffmpeg・インターネット（PeerJS の仲介）が要る）:
    python tests/e2e/bgm_level.py [作業フォルダ]
 見本の写しに、CD の曲くらい大きい曲（1枚目）と、見本の曲くらいの曲（4枚目）を足す →
 語り手の準備の画面で測った大きさが ffmpeg（ebur128）と合う・大きい曲だけ下げると出る →
 聞き手を1台つなぐ → 開演 → 語り手・聞き手の両方で、大きい曲は -30 LUFS まで下げて、もう1曲はそのまま鳴る。
 設計: docs/work-format.md §4。作業用リポジトリの見本は変えない（写しで行う）。"""
import functools
import http.server
import json
import re
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
HERE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix='dk-e2e-'))
HERE.mkdir(parents=True, exist_ok=True)
print(f'work: {HERE}')
ROOT = HERE / 'rt'
WORK = ROOT / 'work'
sys.path.insert(0, str(REPO / 'skills' / 'digital-kamishibai' / 'scripts'))
import burn  # noqa: E402

# 触れる前の音をブラウザが止めないように
_real = subprocess.Popen
burn.subprocess = types.SimpleNamespace(Popen=lambda a, **kw: _real([a[0], '--autoplay-policy=no-user-gesture-required', *a[1:]], **kw),
                                        DEVNULL=subprocess.DEVNULL, TimeoutExpired=subprocess.TimeoutExpired)
BUILD = REPO / 'skills' / 'digital-kamishibai' / 'scripts' / 'build_work.py'
failures = []


def ok(name, cond, detail=''):
    print(f'  {"OK " if cond else "NG "} {name}' + (f'  ({detail})' if detail else ''))
    if not cond:
        failures.append(name)


def ffmpeg(*a):
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', *map(str, a)], check=True)


def lufs(path):
    r = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', str(path), '-af', 'ebur128', '-f', 'null', '-'],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    return float(re.findall(r'I:\s+(-?[\d.]+) LUFS', r.stderr)[-1])


# ---------- 準備: 見本の写しに、大きい曲と見本くらいの曲 ----------
shutil.rmtree(ROOT, ignore_errors=True)
shutil.copytree(REPO / 'examples' / 'sample-story', WORK)
shutil.copytree(REPO / 'player', ROOT / 'player')
(WORK / 'sounds').mkdir(exist_ok=True)
ffmpeg('-f', 'lavfi', '-i', 'sine=frequency=330:duration=60', '-af', 'volume=10dB', '-ac', '2', '-c:a', 'libmp3lame', WORK / 'sounds' / 'loud.mp3')
ffmpeg('-f', 'lavfi', '-i', 'sine=frequency=550:duration=60', '-af', 'volume=-11dB', '-ac', '2', '-c:a', 'libmp3lame', WORK / 'sounds' / 'soft.mp3')
LOUD, SOFT = lufs(WORK / 'sounds' / 'loud.mp3'), lufs(WORK / 'sounds' / 'soft.mp3')
print(f'ffmpeg: loud {LOUD} LUFS / soft {SOFT} LUFS')
assert LOUD > -20 and -34 < SOFT < -30, (LOUD, SOFT)
script = (WORK / 'script.md').read_text(encoding='utf-8')
script = script.replace('## [Slide 1] Cover\n', '## [Slide 1] Cover\n\n> [BGM] sounds/loud.mp3\n', 1)
script = script.replace('## [Slide 4] The end\n', '## [Slide 4] The end\n\n> [BGM once] sounds/soft.mp3\n', 1)
(WORK / 'script.md').write_text(script, encoding='utf-8')
r = subprocess.run([sys.executable, str(BUILD), str(WORK), '--skip-text'], capture_output=True, text=True, encoding='utf-8', errors='replace')
assert r.returncode == 0, r.stdout + r.stderr

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


def open_page(b, url, w, h):
    b.call('Emulation.setDeviceMetricsOverride', {'width': w, 'height': h, 'deviceScaleFactor': 1, 'mobile': False}, session=True)
    b.call('Page.navigate', {'url': url}, session=True)
    time.sleep(1.5)
    b.evaluate(TRAP)


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
    open_page(nar, base + '/player/narrator.html?test', 1600, 1100)
    nar.evaluate(f"localStorage.clear(); {PICK}({json.dumps(files)})")
    wait(nar, "document.getElementById('workTitle').textContent.length > 0", 'work')
    lv = {x['key']: x for x in nar.evaluate("__dk.levels()")}
    print('  語り手が測った大きさ:', json.dumps(lv))
    ok('大きい曲: 測った大きさが ffmpeg と 0.5 LU 以内', abs(lv['sounds/loud.mp3']['lufs'] - LOUD) < 0.5, f"{lv['sounds/loud.mp3']['lufs']:.2f} / {LOUD}")
    ok('見本くらいの曲: 測った大きさが ffmpeg と 0.5 LU 以内', abs(lv['sounds/soft.mp3']['lufs'] - SOFT) < 0.5, f"{lv['sounds/soft.mp3']['lufs']:.2f} / {SOFT}")
    want = -30 - lv['sounds/loud.mp3']['lufs']
    ok('大きい曲だけ -30 LUFS まで下げる。見本くらいの曲は下げない',
       abs(lv['sounds/loud.mp3']['gain'] - want) < 0.11 and lv['sounds/soft.mp3']['gain'] == 0, json.dumps(lv))
    note = nar.evaluate("document.getElementById('levelNote').hidden ? null : document.getElementById('levelNote').textContent")
    ok('準備の画面に、小さくして鳴らす曲が出る（下げない曲は出ない）', bool(note) and 'loud.mp3' in note and 'soft.mp3' not in note, note)

    nar.evaluate("document.querySelector('[data-goto=room]').click(); document.getElementById('expected').value = 1; "
                 "document.getElementById('openRoom').click(); true")
    ok('受付が開く', wait(nar, "/\\d/.test(document.getElementById('code').textContent)", 'code', 600))
    code = nar.evaluate("document.getElementById('code').textContent").replace(' ', '')
    open_page(lis, base + '/player/listen.html?test', 900, 506)
    lis.evaluate(f"document.getElementById('code').value = '{code}'; document.getElementById('name').value = 'far'; "
                 "document.querySelector('input[name=mic][value=listen]').checked = true; "
                 "document.getElementById('joinForm').requestSubmit(); true")
    wait(nar, "document.querySelectorAll('#requests button').length > 0", 'request', 600)
    nar.evaluate("document.querySelector('#requests button').click(); true")
    ok('聞き手に1枚目の絵が出る', wait(lis, "!document.getElementById('picture').hidden && document.getElementById('picture').naturalWidth > 0", 'picture', 600))
    nar.evaluate("document.querySelector('[data-goto=show]').click(); true")
    time.sleep(0.3)
    nar.evaluate("document.getElementById('startShowBar').click(); true")
    amp = 10 ** (want / 20)
    ok('語り手の端末: 大きい曲を小さくして鳴らす', wait(nar, f"__dk.audio().playing && Math.abs(__dk.audio().level - {amp}) < 1e-3", 'narrator level'),
       json.dumps(nar.evaluate("__dk.audio()")))
    ok('聞き手の端末: 大きい曲を同じだけ小さくして鳴らす', wait(lis, f"__dkl.audio().playing && Math.abs(__dkl.audio().level - {amp}) < 1e-3", 'listener level', 600),
       json.dumps(lis.evaluate("__dkl.audio()")))
    for _ in range(3):
        nar.evaluate("document.getElementById('nextBtn').click(); true")
        time.sleep(0.4)
    ok('語り手の端末: 4枚目の曲はそのまま鳴らす', wait(nar, "__dk.audio().playing && __dk.audio().level === 1", 'narrator soft'), json.dumps(nar.evaluate("__dk.audio()")))
    ok('聞き手の端末: 4枚目の曲はそのまま鳴らす', wait(lis, "__dkl.audio().playing && __dkl.audio().level === 1", 'listener soft', 600), json.dumps(lis.evaluate("__dkl.audio()")))
    ok('語り手・聞き手のページに例外が0件', nar.evaluate("window.__errs.length") == 0 and lis.evaluate("window.__errs.length") == 0,
       json.dumps([nar.evaluate("window.__errs"), lis.evaluate("window.__errs")]))
finally:
    nar.close()
    lis.close()
    server.shutdown()

print('ALL OK' if not failures else f'NG {len(failures)}: ' + ' / '.join(failures))
sys.exit(1 if failures else 0)
