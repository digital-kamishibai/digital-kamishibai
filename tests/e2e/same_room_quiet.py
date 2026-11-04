"""語り手と同じ部屋の端末では語り手の声を鳴らさない（ハウリング止め）ことを、語り手と聞き手の端末で確かめる（手で動かす確認。Edge・ffmpeg が要る）:
    python tests/e2e/same_room_quiet.py [作業フォルダ]
 テスト用のマイクに確かめの音の高さ（1800Hz）を流しっぱなしにする＝語り手のマイクは点呼のどの音も「拾った」になる
→ 聞くだけ（マイクなし）の聞き手を1台承認して音の点呼 → その端末へ行く語り手の声の栓が閉じ、聞き手の画面に案内と「鳴らす」が出る
→ 聞き手が「鳴らす」で戻せる・「鳴らさない」でまた止められる → 語り手の札の「鳴らす」でも戻せる。
plans の digital-kamishibai-skill.md 未決2（2026-11-04 決定: 案 A・聞き手の端末からも戻せる）。"""
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
HERE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix='dk-e2e-'))
HERE.mkdir(parents=True, exist_ok=True)
print(f'work: {HERE}')
ROOT = HERE / 'fam'
WORK = ROOT / 'sample'
PY = sys.executable
sys.path.insert(0, str(REPO / 'skills' / 'digital-kamishibai' / 'scripts'))
import burn  # noqa: E402

BUILD = REPO / 'skills' / 'digital-kamishibai' / 'scripts' / 'build_work.py'

_real = subprocess.Popen
TONE = HERE / 'tone.wav'  # 確かめの音の高さ（voice.js の TONE_HZ）。同じ部屋で鳴った音を拾った代わり
subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=1800:duration=10',
                '-af', 'volume=0.5', '-ac', '1', '-ar', '48000', str(TONE)], check=True)
EXTRA = ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', f'--use-file-for-fake-audio-capture={TONE}',
         '--autoplay-policy=no-user-gesture-required']
burn.subprocess = types.SimpleNamespace(Popen=lambda args, **kw: _real([args[0], *EXTRA, *args[1:]], **kw),
                                        DEVNULL=subprocess.DEVNULL, TimeoutExpired=subprocess.TimeoutExpired)

results = []


def ok(name, cond, detail=''):
    results.append((name, bool(cond)))
    print(('  OK  ' if cond else '  NG  ') + name + (f'  [{detail}]' if detail else ''))


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


r = subprocess.run([PY, str(BUILD), str(WORK)], capture_output=True, text=True, encoding='utf-8', errors='replace')
print(f'$ build_work.py -> {r.returncode}')
exe = burn.find_browser()
nar, lis = burn.Browser(exe), burn.Browser(exe)
STATE = "__dk.voice().state"
GAIN = "(Object.values(__dk.voice().narratorTo)[0])"
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
    ok('声の通話が張られ、語り手の声の栓は開いている', wait(nar, f"__dk.voice().calls.length === 1 && {GAIN} === 1", 'call'))
    ok('点呼の前は、聞き手に「鳴らす／鳴らさない」のボタンが出ない', lis.evaluate("document.getElementById('quietBtn').hidden"))

    nar.evaluate("document.getElementById('rollCall').click(); true")
    ok('点呼: 聞くだけの端末も音を鳴らし、語り手と同じ部屋と分かる',
       wait(nar, f"{STATE}.quiet.length === 1", 'quiet', tries=400), nar.evaluate(STATE + '.quiet'))
    ok('点呼の結果に「語り手の声を鳴らしません」が出る', 'ハウリング' in nar.evaluate("document.getElementById('rollResult').textContent")
       or 'howls' in nar.evaluate("document.getElementById('rollResult').textContent"), nar.evaluate("document.getElementById('rollResult').textContent"))
    ok('マイクの無い端末に「声を届けない」は言わない', not any(w in nar.evaluate("document.getElementById('rollResult').textContent") for w in ('1部屋にマイクは1台', 'one mic per room')))
    ok('その端末へ行く語り手の声の栓が閉じる', wait(nar, f"{GAIN} < 0.01", 'gain closed'), nar.evaluate(GAIN))
    ok('語り手のマイクそのものは切らない', nar.evaluate(STATE + '.narratorMic') is True)
    ok('語り手の札に「鳴らす」が出る', nar.evaluate("!!document.querySelector('#chips [data-quiet]')"))
    ok('聞き手に案内と「語り手の声を鳴らす」が出る', wait(lis, "!document.getElementById('quietNote').hidden && !document.getElementById('quietBtn').hidden", 'listener note'))
    shot(lis, 'listener_quiet.png')
    shot(nar, 'narrator_quiet.png')

    lis.evaluate("document.getElementById('quietBtn').click(); true")
    ok('聞き手の「鳴らす」で戻る（栓が開く）', wait(nar, f"{STATE}.quiet.length === 0 && {GAIN} > 0.99", 'resume by listener'))
    ok('戻したあと、聞き手の案内は消え、ボタンは「鳴らさない」になる',
       wait(lis, "document.getElementById('quietNote').hidden && !document.getElementById('quietBtn').hidden", 'listener after'))
    lis.evaluate("document.getElementById('quietBtn').click(); true")
    ok('聞き手の「鳴らさない」でまた止まる', wait(nar, f"{STATE}.quiet.length === 1 && {GAIN} < 0.01", 'quiet by listener'))
    nar.evaluate("document.querySelector('#chips [data-quiet]').click(); true")
    ok('語り手の札の「鳴らす」でも戻る', wait(nar, f"{STATE}.quiet.length === 0 && {GAIN} > 0.99", 'resume by narrator'))
    ok('聞き手の画面も戻る', wait(lis, "document.getElementById('quietNote').hidden", 'listener synced'))
    errs = [nar.evaluate('window.__errs'), lis.evaluate('window.__errs')]
    ok('ページに例外が無い', not any(errs), errs)
finally:
    nar.close()
    lis.close()
    server.shutdown()
print(f'{sum(1 for _, good in results if good)}/{len(results)} OK')
sys.exit(0 if all(good for _, good in results) else 1)
