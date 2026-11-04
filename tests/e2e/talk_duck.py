"""語っているあいだ BGM が下がり、黙ると戻ることを、語り手と聞き手の端末で確かめる（手で動かす確認。Edge・ffmpeg が要る）:
    python tests/e2e/talk_duck.py [作業フォルダ]
 テスト用のマイクに「3秒鳴って3秒黙る」音を流す（--use-file-for-fake-audio-capture）→ 見本の写しに BGM を足して受付を開き、
聞き手を1台承認して開演 → 語り手と聞き手の BGM（engine.state().talking）が、鳴っているあいだ下がり、黙ると戻る。
「話しているあいだ BGM を下げる」を切ると下がらない。plans の kamishibai-player-talk-duck.md（2026-10-26）。"""
import base64
import functools
import http.server
import json
import shutil
import subprocess
import sys
import threading
import tempfile
import time
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# 作業場所（見本の写し・撮った画面）。引数で渡さなければ一時フォルダ
HERE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix='dk-e2e-'))
HERE.mkdir(parents=True, exist_ok=True)
print(f'work: {HERE}')
ROOT = HERE / 'fam'
WORK = ROOT / 'sample'
PY = sys.executable
sys.path.insert(0, str(REPO / 'skills' / 'digital-kamishibai' / 'scripts'))
import burn  # noqa: E402

BUILD = REPO / 'skills' / 'digital-kamishibai' / 'scripts' / 'build_work.py'
CHECK = REPO / 'skills' / 'digital-kamishibai' / 'scripts' / 'check_sheet.py'

# マイクを使う画面なので、偽のマイクで許可の確認を出さない
_real = subprocess.Popen
SPEECH = HERE / 'speech.wav'      # 3秒鳴って3秒黙る（声の代わり。ブラウザは繰り返し流す）
subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=220:duration=3', '-f', 'lavfi', '-i',
                'anullsrc=r=48000:cl=mono', '-filter_complex', '[0:a]aresample=48000,volume=0.3[a];[1:a]atrim=duration=3[b];[a][b]concat=n=2:v=0:a=1',
                '-ac', '1', '-ar', '48000', str(SPEECH)], check=True)
EXTRA = ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', f'--use-file-for-fake-audio-capture={SPEECH}',
         '--autoplay-policy=no-user-gesture-required']
burn.subprocess = types.SimpleNamespace(Popen=lambda args, **kw: _real([args[0], *EXTRA, *args[1:]], **kw),
                                        DEVNULL=subprocess.DEVNULL, TimeoutExpired=subprocess.TimeoutExpired)

results = []


def ok(name, cond, detail=''):
    results.append((name, bool(cond)))
    print(('  OK  ' if cond else '  NG  ') + name + (f'  [{detail}]' if detail else ''))


def run(*args):
    r = subprocess.run([PY, *map(str, args)], capture_output=True, text=True, encoding='utf-8', errors='replace')
    print(f'$ {Path(str(args[0])).name} {" ".join(map(str, args[2:]))} -> {r.returncode}')
    return r


shutil.rmtree(ROOT, ignore_errors=True)
shutil.copytree(REPO / 'examples' / 'sample-story', WORK)
shutil.copytree(REPO / 'player', ROOT / 'player')


class Quiet(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      '.js': 'text/javascript', '.mjs': 'text/javascript'}

    def log_message(self, *a):
        pass


server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(ROOT)))
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f'http://127.0.0.1:{server.server_address[1]}'


def listing():
    return [{'url': '/' + p.relative_to(ROOT).as_posix(), 'rel': p.relative_to(ROOT).as_posix(),
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
TRAP = ("window.__errs = []; addEventListener('error', (e) => __errs.push(e.message)); "
        "addEventListener('unhandledrejection', (e) => __errs.push(String(e.reason))); true")


def wait(b, js, what, tries=600):
    for _ in range(tries):
        try:
            if b.evaluate(js):
                return True
        except burn.BurnError:
            pass
        time.sleep(0.05)
    print('  timeout: ' + what)
    return False


def page(b, url, w=1600, h=1300):
    b.call('Emulation.setDeviceMetricsOverride', {'width': w, 'height': h, 'deviceScaleFactor': 1, 'mobile': False}, session=True)
    b.call('Page.navigate', {'url': url}, session=True)
    time.sleep(1.0)
    b.evaluate(TRAP)


def shot(b, name):
    (HERE / name).write_bytes(base64.b64decode(b.call('Page.captureScreenshot', {'format': 'png'}, session=True)['data']))


exe = burn.find_browser()
(WORK / 'sounds').mkdir(exist_ok=True)
subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=550:duration=120', '-c:a', 'libmp3lame', str(WORK / 'sounds' / 'bgm.mp3')], check=True)
s = (WORK / 'script.md').read_text(encoding='utf-8').replace('## [Slide 1] Cover\n', '## [Slide 1] Cover\n\n> [BGM] sounds/bgm.mp3\n', 1)
(WORK / 'script.md').write_text(s, encoding='utf-8')
run(BUILD, WORK)
nar, lis = burn.Browser(exe), burn.Browser(exe)


def watch(b, js, secs=8):
    seen = set()
    for _ in range(int(secs / 0.1)):
        seen.add(bool(b.evaluate(js)))
        time.sleep(0.1)
    return seen


try:
    page(nar, base + '/player/narrator.html?test')
    nar.evaluate(f"{PICK}('pickWork', {json.dumps(listing())})")
    wait(nar, "document.getElementById('workTitle').textContent.length > 0", 'work')
    nar.evaluate("document.querySelector('[data-goto=room]').click(); document.getElementById('expected').value = 1; document.getElementById('openRoom').click(); true")
    ok('受付が開く', wait(nar, "/\\d/.test(document.getElementById('code').textContent)", 'code'))
    code = nar.evaluate("document.getElementById('code').textContent").replace(' ', '')
    page(lis, base + '/player/listen.html?test', 900, 600)
    lis.evaluate(f"document.getElementById('code').value = '{code}'; document.getElementById('name').value = 'tester'; "
                 "document.querySelector('input[name=mic][value=listen]').checked = true; "
                 "document.getElementById('joinForm').requestSubmit(); true")
    wait(nar, "document.querySelectorAll('#requests button').length > 0", 'request')
    nar.evaluate("document.querySelector('#requests button').click(); true")
    wait(lis, "!!document.querySelector('#pic, img') && window.__dkl", 'approved')
    time.sleep(1.5)
    lis.evaluate("document.body.click(); true")                        # 聞き手の端末で音を出せるように
    nar.evaluate("document.getElementById('startShowBar').click(); true")
    ok('開演で BGM が鳴る（語り手）', wait(nar, "__dk.audio().playing", 'bgm narrator'))
    ok('語り手の「自分のマイク」が入', wait(nar, "__dk.session && document.getElementById('micSelf').textContent.includes('入') || document.getElementById('micSelf').textContent.includes('on')", 'mic on', tries=100))
    n_seen = watch(nar, "__dk.audio().talking")
    ok('語り手: 鳴っているあいだ下がり、黙ると戻る', n_seen == {True, False}, n_seen)
    # 「BGM を下げ中」の印が出たり消えたりしても、帯の下（戻る／次へ）が動かない（2026-10-27 練習した人「クリック位置が変わるのは致命的」）
    lamp = watch(nar, "!getComputedStyle(document.getElementById('talkLamp')).visibility.startsWith('h')")
    ok('「BGM を下げ中」の印が点いて消える', lamp == {True, False}, lamp)
    tops = set()
    for _ in range(80):
        tops.add(round(nar.evaluate("document.getElementById('nextBtn').getBoundingClientRect().top")))
        time.sleep(0.1)
    ok('印が出入りしても「次へ」の位置が動かない', len(tops) == 1, sorted(tops))
    l_seen = watch(lis, "__dkl.audio().talking")
    ok('聞き手: 語り手の合図で下がり、戻る', l_seen == {True, False}, l_seen)
    nar.evaluate("(() => { const c = document.getElementById('talkDuck'); c.checked = false; c.dispatchEvent(new Event('change')); return true; })()")
    time.sleep(0.3)
    ok('切ると下がらない（語り手・聞き手）', watch(nar, "__dk.audio().talking", 7) == {False} and watch(lis, "__dkl.audio().talking", 1) == {False})
    errs = [nar.evaluate('window.__errs'), lis.evaluate('window.__errs')]
    ok('ページに例外が無い', not any(errs), errs)
finally:
    nar.close()
    lis.close()
    server.shutdown()
print(f'{sum(1 for _, good in results if good)}/{len(results)} OK')
sys.exit(0 if all(good for _, good in results) else 1)
