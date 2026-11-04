"""語り手の札に、聞き手の端末の道（直接／中継）が出ることを確かめる（手で動かす確認。Edge が要る）:
    python tests/e2e/route_chip.py [作業フォルダ]
 受付を開き、聞き手を1台承認 → 語り手の受付の一覧と上演の札に「直接」が出る（同じ PC の2つのブラウザなので直接つながる）→
聞き手の画面には道を出さない。中継の札（「中継」）と、中継まわりの案内は TURN を有効にした環境でしか出ないので、
判定は tests/player/ice.test.js の whyBlocked・routeOf で見る。plans の digital-kamishibai-skill.md 未決2 段1（2026-11-02）。"""
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

# マイクを使う画面なので、偽のマイクで許可の確認を出さない
_real = subprocess.Popen
EXTRA = ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--autoplay-policy=no-user-gesture-required']
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
ROUTE = "/直接|direct|中継|via relay/.exec(document.getElementById('listeners').textContent)?.[0] || ''"
CHIP = "/直接|direct|中継|via relay/.exec(document.getElementById('chips').textContent)?.[0] || ''"


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
r = subprocess.run([PY, str(BUILD), str(WORK)], capture_output=True, text=True, encoding='utf-8', errors='replace')
print(f'$ build_work.py -> {r.returncode}')
nar, lis = burn.Browser(exe), burn.Browser(exe)
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
    # 道は5秒おきに読み直すので、最大12秒待つ
    ok('受付の聞き手一覧に道が出る', wait(nar, ROUTE, 'route', tries=240), nar.evaluate(ROUTE))
    ok('同じ PC どうしは「直接」', nar.evaluate(ROUTE) in ('直接', 'direct'), nar.evaluate(ROUTE))
    shot(nar, 'route_chip_room.png')
    nar.evaluate("document.querySelector('[data-goto=show]').click(); true")
    ok('上演の画面の札にも道が出る', wait(nar, CHIP, 'chip', tries=100), nar.evaluate(CHIP))
    shot(nar, 'route_chip_show.png')
    listener_text = lis.evaluate("document.body.innerText")
    ok('聞き手の画面には道を出さない', not any(w in listener_text for w in ('直接', '中継', 'via relay')), '')
    errs = [nar.evaluate('window.__errs'), lis.evaluate('window.__errs')]
    ok('ページに例外が無い', not any(errs), errs)
finally:
    nar.close()
    lis.close()
    server.shutdown()
print(f'{sum(1 for _, good in results if good)}/{len(results)} OK')
sys.exit(0 if all(good for _, good in results) else 1)
