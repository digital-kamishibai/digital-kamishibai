"""動画を流し始めたら BGM が止まり、動画のあとも鳴らし直さないことを、語り手の端末で鳴っている音で確かめる（Edge・ffmpeg が要る）:
    python tests/e2e/bgm_video.py [作業フォルダ]
 見本の写しに BGM（1枚目から）と短い動画（2枚目）を足す → 聞き手なしで開演（練習と同じ）→ 2枚目で動画を最後まで流す →
BGM は止まったまま → 3枚目でも止まったまま → 4枚目の [BGM] で次の曲が鳴る。
⚠️ 見るのは語り手の側の記録（session.audio）ではなく、実際に鳴らしている音（engine）。2026-10-26 に、記録は止まったのに
聞き手のいない練習では音が鳴り続けた（止める合図の宛先が0人のとき、語り手の端末の音も止めていなかった）。
作業用リポジトリの見本は変えない（写しで行う）。"""
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
HERE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix='dk-e2e-'))
HERE.mkdir(parents=True, exist_ok=True)
print(f'work: {HERE}')
WORK = HERE / 'rt' / 'work'
sys.path.insert(0, str(REPO / 'skills' / 'digital-kamishibai' / 'scripts'))
import burn  # noqa: E402

# 触れる前の音をブラウザが止めないように（開演のボタンは音の許可を待つ）
_real = subprocess.Popen
burn.subprocess = types.SimpleNamespace(Popen=lambda args, **kw: _real([args[0], '--autoplay-policy=no-user-gesture-required', *args[1:]], **kw),
                                        DEVNULL=subprocess.DEVNULL, TimeoutExpired=subprocess.TimeoutExpired)
BUILD = REPO / 'skills' / 'digital-kamishibai' / 'scripts' / 'build_work.py'


def ffmpeg(*a):
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', *map(str, a)], check=True)


# ---------- 準備: 見本の写しに BGM 2曲と動画1本 ----------
shutil.rmtree(HERE / 'rt', ignore_errors=True)
shutil.copytree(REPO / 'examples' / 'sample-story', WORK)
(WORK / 'sounds').mkdir(exist_ok=True)
(WORK / 'videos').mkdir(exist_ok=True)
ffmpeg('-f', 'lavfi', '-i', 'sine=frequency=330:duration=60', '-c:a', 'libmp3lame', WORK / 'sounds' / 'first.mp3')
ffmpeg('-f', 'lavfi', '-i', 'sine=frequency=550:duration=60', '-c:a', 'libmp3lame', WORK / 'sounds' / 'next.mp3')
ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=25:duration=4', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=4',
       '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', WORK / 'videos' / 'clip.mp4')
script = (WORK / 'script.md').read_text(encoding='utf-8')
script = script.replace('## [Slide 1] Cover\n', '## [Slide 1] Cover\n\n> [BGM] sounds/first.mp3\n', 1)
script = script.replace('> [Picture] pictures/02.png\n', '> [Picture] pictures/02.png\n\n> [Video] videos/clip.mp4\n', 1)
script = script.replace('## [Slide 4] The end\n', '## [Slide 4] The end\n\n> [BGM] sounds/next.mp3\n', 1)
(WORK / 'script.md').write_text(script, encoding='utf-8')
r = subprocess.run([sys.executable, str(BUILD), str(WORK), '--draft', '--skip-text'], capture_output=True, text=True, encoding='utf-8', errors='replace')
assert r.returncode == 0, r.stdout + r.stderr
w = json.loads((WORK / 'work.json').read_text(encoding='utf-8'))
assert [c['type'] for c in w['slides'][1]['cues']].count('video') == 1 and w['slides'][0]['cues'][0]['type'] == 'bgm'

site = HERE / 'rt' / 'site'
shutil.copytree(REPO / 'player', site / 'player')


class Quiet(http.server.SimpleHTTPRequestHandler):
    # ⚠️ Windows では .js が text/javascript で返らないことがある（モジュールが読めない）
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      '.js': 'text/javascript', '.mjs': 'text/javascript'}

    def log_message(self, *a):
        pass


server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(HERE / 'rt')))
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f'http://127.0.0.1:{server.server_address[1]}'
files = [{'url': '/' + p.relative_to(HERE / 'rt').as_posix(), 'rel': p.relative_to(WORK.parent).as_posix(),
          'mtime': int(p.stat().st_mtime * 1000)} for p in WORK.rglob('*') if p.is_file()]
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
# 実際に鳴らしている BGM（engine）と、その曲のファイル名
NOW = """(() => { const e = __dk.audio(); const name = (f) => __dk.audioId(f);
  const which = e.bgm === name('sounds/first.mp3') ? 'first' : e.bgm === name('sounds/next.mp3') ? 'next' : e.bgm;
  return { slide: __dk.session().slide, bgm: which, playing: e.playing }; })()"""

b = burn.Browser(burn.find_browser())
ev = b.evaluate


def wait(js, what, tries=600):
    for _ in range(tries):
        try:
            if ev(js):
                return
        except burn.BurnError:
            pass
        time.sleep(0.05)
    raise SystemExit(f'timeout: {what}')


def step(label, want_bgm):
    got = ev(NOW)
    print(f'{label}: {got}')
    assert got['bgm'] == want_bgm and got['playing'] == (want_bgm is not None), f'{label}: BGM が {got}（期待 {want_bgm}）'


try:
    b.call('Page.navigate', {'url': base + '/site/player/narrator.html?test'}, session=True)
    wait("!!document.getElementById('pickWork')", 'page')
    time.sleep(0.5)
    ev("localStorage.clear(); window.__errs = []; addEventListener('error', (e) => __errs.push(e.message)); "
       "addEventListener('unhandledrejection', (e) => __errs.push(String(e.reason))); true")
    ev(f"{PICK}({json.dumps(files)})")
    wait("document.getElementById('workTitle').textContent.length > 0", 'work loaded')
    ev("document.querySelector('[data-goto=show]').click(); true")
    time.sleep(0.3)
    ev("document.getElementById('startShowBar').click(); true")   # 聞き手なしで開演（練習と同じ）
    wait("__dk.audio().playing", 'bgm started')
    step('1枚目（開演）', 'first')
    ev("document.getElementById('nextBtn').click(); true")
    time.sleep(0.5)
    step('2枚目（動画の前）', 'first')
    wait("document.getElementById('nvideo').readyState >= 1", 'video')
    ev("(async () => { const v = document.getElementById('nvideo'); v.muted = true; await v.play(); return true; })()")
    time.sleep(0.5)
    step('2枚目（動画を流し始めた）', None)
    wait("document.getElementById('nvideo').ended", 'video ended', tries=200)
    time.sleep(1.0)
    step('2枚目（動画が終わった）', None)
    ev("document.getElementById('nextBtn').click(); true")
    time.sleep(0.5)
    step('3枚目（同じ曲が続く枚）', None)
    ev("document.getElementById('nextBtn').click(); true")
    wait("__dk.audio().playing", 'next bgm', tries=200)
    step('4枚目（次の [BGM]）', 'next')
    errs = ev('window.__errs')
    print('ページの例外:', errs)
    assert not errs
    print('ALL OK')
finally:
    b.close()
    server.shutdown()
